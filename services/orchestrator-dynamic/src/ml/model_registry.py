"""
Model Registry para MLflow Integration.

Gerencia ciclo de vida de modelos ML: versionamento, registro, promoção e carregamento.
"""

from typing import Any, Dict, List, Optional, Tuple
from functools import lru_cache
from datetime import datetime
import asyncio
import structlog
from mlflow.tracking import MlflowClient
import mlflow
import mlflow.sklearn

logger = structlog.get_logger(__name__)


# Importar metrics no nível de módulo para evitar dependência circular
_metrics_instance = None


def _get_metrics():
    """Helper para obter metrics singleton."""
    global _metrics_instance
    if _metrics_instance is None:
        from src.observability.metrics import get_metrics
        _metrics_instance = get_metrics()
    return _metrics_instance


class ModelRegistry:
    """
    Gerencia registro e ciclo de vida de modelos no MLflow.

    Responsável por:
    - Conexão com MLflow Tracking Server
    - Registro de modelos treinados
    - Versionamento e promoção de modelos
    - Carregamento de modelos em produção
    - Cache de modelos em memória
    """

    def __init__(self, config):
        """
        Inicializa Model Registry.

        Args:
            config: Configuração com mlflow_tracking_uri e mlflow_experiment_name
        """
        self.config = config
        self.tracking_uri = config.mlflow_tracking_uri
        self.experiment_name = config.mlflow_experiment_name
        self.client: Optional[MlflowClient] = None
        self.experiment_id: Optional[str] = None
        # Cache: {cache_key: (model, loaded_timestamp)}
        self._model_cache: Dict[str, Tuple[Any, float]] = {}
        self.cache_ttl_seconds = config.ml_model_cache_ttl_seconds
        self.logger = logger.bind(component="model_registry")

    async def initialize(self):
        """
        Inicializa conexão com MLflow e cria experimento se necessário.
        """
        try:
            # Configura MLflow tracking URI
            mlflow.set_tracking_uri(self.tracking_uri)
            self.client = MlflowClient(tracking_uri=self.tracking_uri)

            # Cria ou obtém experimento
            self.experiment_id = await self._create_experiment_if_not_exists(
                self.experiment_name
            )

            self.logger.info(
                "mlflow_initialized",
                tracking_uri=self.tracking_uri,
                experiment_id=self.experiment_id,
                experiment_name=self.experiment_name
            )

        except Exception as e:
            self.logger.error("mlflow_initialization_failed", error=str(e))
            raise

    async def _create_experiment_if_not_exists(self, experiment_name: str) -> str:
        """
        Cria experimento MLflow se não existir.

        Args:
            experiment_name: Nome do experimento

        Returns:
            ID do experimento
        """
        try:
            # Executa operação sync em thread separada
            experiment = await asyncio.to_thread(
                self.client.get_experiment_by_name,
                experiment_name
            )
            if experiment:
                return experiment.experiment_id

            # Cria novo experimento em thread separada
            experiment_id = await asyncio.to_thread(
                self.client.create_experiment,
                name=experiment_name,
                tags={
                    'project': 'neural-hive-mind',
                    'component': 'orchestrator-dynamic',
                    'purpose': 'predictive-modeling'
                }
            )

            self.logger.info("mlflow_experiment_created", experiment_id=experiment_id)
            return experiment_id

        except Exception as e:
            self.logger.error("experiment_creation_failed", error=str(e))
            raise

    def _save_model_sync(
        self,
        model: Any,
        model_name: str,
        metrics: Dict[str, float],
        params: Dict[str, Any],
        tags: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Helper síncrono para salvar modelo no MLflow.

        Args:
            model: Modelo treinado (scikit-learn)
            model_name: Nome do modelo no registry
            metrics: Métricas de avaliação (MAE, RMSE, R2, etc)
            params: Hiperparâmetros do modelo
            tags: Tags adicionais (opcional)

        Returns:
            Run ID do MLflow
        """
        with mlflow.start_run(experiment_id=self.experiment_id) as run:
            # Log parâmetros
            mlflow.log_params(params)

            # Log métricas
            mlflow.log_metrics(metrics)

            # Log tags
            if tags:
                mlflow.set_tags(tags)

            # Log modelo com sklearn flavor
            mlflow.sklearn.log_model(
                sk_model=model,
                artifact_path="model",
                registered_model_name=model_name
            )

            return run.info.run_id

    async def save_model(
        self,
        model: Any,
        model_name: str,
        metrics: Dict[str, float],
        params: Dict[str, Any],
        tags: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Salva modelo no MLflow com métricas e parâmetros.

        Args:
            model: Modelo treinado (scikit-learn)
            model_name: Nome do modelo no registry
            metrics: Métricas de avaliação (MAE, RMSE, R2, etc)
            params: Hiperparâmetros do modelo
            tags: Tags adicionais (opcional)

        Returns:
            Run ID do MLflow
        """
        try:
            # Executa operação sync em thread separada
            run_id = await asyncio.to_thread(
                self._save_model_sync,
                model,
                model_name,
                metrics,
                params,
                tags
            )

            self.logger.info(
                "model_saved",
                model_name=model_name,
                run_id=run_id,
                metrics=metrics
            )

            # Limpa cache após salvar novo modelo
            self._model_cache.pop(model_name, None)

            return run_id

        except Exception as e:
            self.logger.error("model_save_failed", model_name=model_name, error=str(e))
            raise

    async def load_model(
        self,
        model_name: str,
        version: str = 'latest',
        stage: str = 'Production'
    ) -> Optional[Any]:
        """
        Carrega modelo do MLflow.

        Tenta carregar da stage Production primeiro, depois latest version.
        Usa cache LRU para modelos carregados.

        Args:
            model_name: Nome do modelo no registry
            version: Versão específica ou 'latest' (default: 'latest')
            stage: Stage do modelo (default: 'Production')

        Returns:
            Modelo carregado ou None se não encontrado
        """
        try:
            # Verifica cache com TTL
            cache_key = f"{model_name}_{stage}_{version}"
            if cache_key in self._model_cache:
                cached_model, loaded_at = self._model_cache[cache_key]
                elapsed = datetime.utcnow().timestamp() - loaded_at

                if elapsed < self.cache_ttl_seconds:
                    self.logger.debug("model_loaded_from_cache", model_name=model_name, age_seconds=elapsed)
                    return cached_model
                else:
                    # Cache expirado, remove entrada
                    self.logger.debug("cache_expired", model_name=model_name, age_seconds=elapsed)
                    del self._model_cache[cache_key]

            # Tenta carregar da stage Production
            try:
                model_uri = f"models:/{model_name}/{stage}"
                # Executa carregamento em thread separada
                model = await asyncio.to_thread(
                    mlflow.sklearn.load_model,
                    model_uri
                )
                # Armazena com timestamp
                self._model_cache[cache_key] = (model, datetime.utcnow().timestamp())
                self.logger.info("model_loaded", model_name=model_name, stage=stage)
                return model
            except Exception:
                # Se falhar, tenta carregar latest version
                pass

            # Tenta carregar última versão
            try:
                # Busca versões em thread separada
                versions = await asyncio.to_thread(
                    self.client.search_model_versions,
                    f"name='{model_name}'"
                )
                if not versions:
                    self.logger.warning("model_not_found", model_name=model_name)
                    return None

                # Ordena por versão (mais recente primeiro)
                versions = sorted(versions, key=lambda v: int(v.version), reverse=True)
                latest_version = versions[0]

                model_uri = f"models:/{model_name}/{latest_version.version}"
                # Executa carregamento em thread separada
                model = await asyncio.to_thread(
                    mlflow.sklearn.load_model,
                    model_uri
                )

                # Armazena com timestamp
                self._model_cache[cache_key] = (model, datetime.utcnow().timestamp())
                self.logger.info(
                    "model_loaded",
                    model_name=model_name,
                    version=latest_version.version
                )
                return model

            except Exception as e:
                self.logger.error("model_load_failed", model_name=model_name, error=str(e))
                return None

        except Exception as e:
            self.logger.error("model_load_error", model_name=model_name, error=str(e))
            return None

    async def get_model_metadata(self, model_name: str) -> Dict[str, Any]:
        """
        Recupera metadados do modelo (métricas, params, versão).

        Args:
            model_name: Nome do modelo

        Returns:
            Dict com metadados do modelo
        """
        try:
            # Executa operação sync em thread separada
            versions = await asyncio.to_thread(
                self.client.search_model_versions,
                f"name='{model_name}'"
            )
            if not versions:
                return {}

            # Pega versão mais recente
            latest = sorted(versions, key=lambda v: int(v.version), reverse=True)[0]

            # Busca run associado em thread separada
            run = await asyncio.to_thread(
                self.client.get_run,
                latest.run_id
            )

            return {
                'model_name': model_name,
                'version': latest.version,
                'stage': latest.current_stage,
                'run_id': latest.run_id,
                'metrics': run.data.metrics,
                'params': run.data.params,
                'tags': run.data.tags
            }

        except Exception as e:
            self.logger.error("get_metadata_failed", model_name=model_name, error=str(e))
            return {}

    async def promote_model(
        self,
        model_name: str,
        version: str,
        stage: str = 'Production'
    ):
        """
        Promove versão do modelo para stage (Production, Staging, etc).

        Critérios de promoção:
        - duration-predictor: MAE < 15%
        - anomaly-detector: precision > 0.75

        Args:
            model_name: Nome do modelo
            version: Versão a promover
            stage: Stage de destino (default: 'Production')
        """
        try:
            # Valida critérios de promoção
            metadata = await self.get_model_metadata(model_name)
            metrics = metadata.get('metrics', {})

            should_promote = False

            if 'duration' in model_name.lower():
                # Duration predictor: MAE < 15%
                mae_pct = metrics.get('mae_percentage', 100.0)
                should_promote = mae_pct < 15.0
                self.logger.info(
                    "duration_model_promotion_check",
                    mae_pct=mae_pct,
                    threshold=15.0,
                    will_promote=should_promote
                )

            elif 'anomaly' in model_name.lower():
                # Anomaly detector: precision > 0.75
                precision = metrics.get('precision', 0.0)
                should_promote = precision > 0.75
                self.logger.info(
                    "anomaly_model_promotion_check",
                    precision=precision,
                    threshold=0.75,
                    will_promote=should_promote
                )

            if not should_promote:
                self.logger.warning(
                    "model_promotion_skipped",
                    model_name=model_name,
                    version=version,
                    reason="metrics_below_threshold"
                )
                return

            # Promove modelo em thread separada
            await asyncio.to_thread(
                self.client.transition_model_version_stage,
                name=model_name,
                version=version,
                stage=stage,
                archive_existing_versions=True
            )

            # Limpa cache
            self._model_cache.clear()

            # Registra métricas do modelo promovido
            try:
                metrics_obj = _get_metrics()
                model_type = 'duration' if 'duration' in model_name.lower() else 'anomaly'

                # Atualiza gauges com métricas de produção
                if 'duration' in model_name.lower():
                    if 'mae_percentage' in metrics:
                        metrics_obj.ml_model_accuracy.labels(
                            model_name=model_name,
                            metric_type='mae_pct_production'
                        ).set(metrics.get('mae_percentage'))
                    if 'r2' in metrics:
                        metrics_obj.ml_model_accuracy.labels(
                            model_name=model_name,
                            metric_type='r2_production'
                        ).set(metrics.get('r2'))
                elif 'anomaly' in model_name.lower():
                    if 'precision' in metrics:
                        metrics_obj.ml_model_accuracy.labels(
                            model_name=model_name,
                            metric_type='precision_production'
                        ).set(metrics.get('precision'))
                    if 'recall' in metrics:
                        metrics_obj.ml_model_accuracy.labels(
                            model_name=model_name,
                            metric_type='recall_production'
                        ).set(metrics.get('recall'))
                    if 'f1_score' in metrics:
                        metrics_obj.ml_model_accuracy.labels(
                            model_name=model_name,
                            metric_type='f1_production'
                        ).set(metrics.get('f1_score'))
            except Exception as e:
                self.logger.warning("failed_to_record_production_metrics", error=str(e))

            self.logger.info(
                "model_promoted",
                model_name=model_name,
                version=version,
                stage=stage
            )

        except Exception as e:
            self.logger.error("model_promotion_failed", error=str(e))
            raise

    async def list_models(self) -> List[Dict[str, Any]]:
        """
        Lista todos os modelos registrados com metadados.

        Returns:
            Lista de dicts com informações dos modelos
        """
        try:
            # Executa operação sync em thread separada
            registered_models = await asyncio.to_thread(
                self.client.search_registered_models
            )

            models = []
            for rm in registered_models:
                # Busca versões em thread separada
                versions = await asyncio.to_thread(
                    self.client.search_model_versions,
                    f"name='{rm.name}'"
                )
                latest = sorted(versions, key=lambda v: int(v.version), reverse=True)[0] if versions else None

                models.append({
                    'name': rm.name,
                    'latest_version': latest.version if latest else None,
                    'current_stage': latest.current_stage if latest else None,
                    'description': rm.description,
                    'tags': rm.tags
                })

            return models

        except Exception as e:
            self.logger.error("list_models_failed", error=str(e))
            return []

    async def compare_models(
        self,
        model_name: str,
        version_a: str,
        version_b: str
    ) -> Dict[str, Any]:
        """
        Compara duas versões de um modelo.

        Args:
            model_name: Nome do modelo
            version_a: Primeira versão
            version_b: Segunda versão

        Returns:
            Dict com comparação de métricas e recomendação
        """
        try:
            # Busca versões em thread separada
            versions = await asyncio.to_thread(
                self.client.search_model_versions,
                f"name='{model_name}'"
            )

            versions_dict = {v.version: v for v in versions}

            if version_a not in versions_dict or version_b not in versions_dict:
                return {'error': 'Uma ou ambas versões não encontradas'}

            v_a = versions_dict[version_a]
            v_b = versions_dict[version_b]

            # Busca runs associados
            run_a = await asyncio.to_thread(self.client.get_run, v_a.run_id)
            run_b = await asyncio.to_thread(self.client.get_run, v_b.run_id)

            metrics_a = run_a.data.metrics
            metrics_b = run_b.data.metrics

            # Calcular diferenças
            comparison = {
                'model_name': model_name,
                'version_a': {
                    'version': version_a,
                    'stage': v_a.current_stage,
                    'metrics': metrics_a,
                    'created_at': v_a.creation_timestamp
                },
                'version_b': {
                    'version': version_b,
                    'stage': v_b.current_stage,
                    'metrics': metrics_b,
                    'created_at': v_b.creation_timestamp
                },
                'differences': {}
            }

            # Calcular diferenças percentuais para cada métrica
            all_metrics = set(metrics_a.keys()) | set(metrics_b.keys())
            for metric in all_metrics:
                val_a = metrics_a.get(metric)
                val_b = metrics_b.get(metric)

                if val_a is not None and val_b is not None and val_a != 0:
                    pct_change = ((val_b - val_a) / abs(val_a)) * 100
                    comparison['differences'][metric] = {
                        'value_a': val_a,
                        'value_b': val_b,
                        'change_pct': round(pct_change, 2)
                    }

            # Determinar recomendação
            recommendation = self._determine_recommendation(
                model_name, metrics_a, metrics_b
            )
            comparison['recommendation'] = recommendation

            self.logger.info(
                "models_compared",
                model_name=model_name,
                version_a=version_a,
                version_b=version_b,
                recommendation=recommendation['preferred_version']
            )

            return comparison

        except Exception as e:
            self.logger.error(
                "compare_models_failed",
                model_name=model_name,
                error=str(e)
            )
            return {'error': str(e)}

    def _determine_recommendation(
        self,
        model_name: str,
        metrics_a: Dict[str, float],
        metrics_b: Dict[str, float]
    ) -> Dict[str, Any]:
        """Determina qual versão é recomendada baseado nas métricas."""
        if 'duration' in model_name.lower():
            # Para duration: menor MAE é melhor
            mae_a = metrics_a.get('mae', metrics_a.get('mae_percentage', float('inf')))
            mae_b = metrics_b.get('mae', metrics_b.get('mae_percentage', float('inf')))

            return {
                'preferred_version': 'a' if mae_a <= mae_b else 'b',
                'reason': f"MAE: {mae_a:.4f} vs {mae_b:.4f}",
                'primary_metric': 'mae'
            }

        elif 'anomaly' in model_name.lower():
            # Para anomaly: maior F1 é melhor
            f1_a = metrics_a.get('f1_score', metrics_a.get('f1', 0))
            f1_b = metrics_b.get('f1_score', metrics_b.get('f1', 0))

            return {
                'preferred_version': 'a' if f1_a >= f1_b else 'b',
                'reason': f"F1: {f1_a:.4f} vs {f1_b:.4f}",
                'primary_metric': 'f1_score'
            }

        return {
            'preferred_version': 'unknown',
            'reason': 'Tipo de modelo não reconhecido',
            'primary_metric': None
        }

    async def get_model_history(
        self,
        model_name: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Recupera histórico de versões do modelo.

        Args:
            model_name: Nome do modelo
            limit: Número máximo de versões (default: 10)

        Returns:
            Lista de versões ordenadas da mais recente para a mais antiga
        """
        try:
            versions = await asyncio.to_thread(
                self.client.search_model_versions,
                f"name='{model_name}'"
            )

            if not versions:
                return []

            # Ordena por versão (mais recente primeiro)
            sorted_versions = sorted(
                versions,
                key=lambda v: int(v.version),
                reverse=True
            )[:limit]

            history = []
            for v in sorted_versions:
                # Busca run associado
                try:
                    run = await asyncio.to_thread(self.client.get_run, v.run_id)
                    metrics = run.data.metrics
                    params = run.data.params
                except Exception:
                    metrics = {}
                    params = {}

                history.append({
                    'version': v.version,
                    'stage': v.current_stage,
                    'run_id': v.run_id,
                    'created_at': v.creation_timestamp,
                    'metrics': metrics,
                    'params': params,
                    'status': v.status
                })

            self.logger.debug(
                "model_history_retrieved",
                model_name=model_name,
                versions_count=len(history)
            )

            return history

        except Exception as e:
            self.logger.error(
                "get_model_history_failed",
                model_name=model_name,
                error=str(e)
            )
            return []

    async def get_best_model(
        self,
        model_name: str,
        metric_name: str,
        minimize: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Encontra a melhor versão do modelo baseado em uma métrica.

        Args:
            model_name: Nome do modelo
            metric_name: Nome da métrica para otimizar
            minimize: Se True, menor é melhor (default: True)

        Returns:
            Dict com informações da melhor versão ou None
        """
        try:
            versions = await asyncio.to_thread(
                self.client.search_model_versions,
                f"name='{model_name}'"
            )

            if not versions:
                return None

            best_version = None
            best_metric_value = float('inf') if minimize else float('-inf')

            for v in versions:
                try:
                    run = await asyncio.to_thread(self.client.get_run, v.run_id)
                    metric_value = run.data.metrics.get(metric_name)

                    if metric_value is None:
                        continue

                    is_better = (
                        metric_value < best_metric_value if minimize
                        else metric_value > best_metric_value
                    )

                    if is_better:
                        best_metric_value = metric_value
                        best_version = {
                            'version': v.version,
                            'stage': v.current_stage,
                            'run_id': v.run_id,
                            metric_name: metric_value,
                            'metrics': run.data.metrics,
                            'params': run.data.params
                        }

                except Exception:
                    continue

            if best_version:
                self.logger.info(
                    "best_model_found",
                    model_name=model_name,
                    version=best_version['version'],
                    metric_name=metric_name,
                    metric_value=best_metric_value
                )

            return best_version

        except Exception as e:
            self.logger.error(
                "get_best_model_failed",
                model_name=model_name,
                error=str(e)
            )
            return None

    async def rollback_model(
        self,
        model_name: str,
        target_version: Optional[str] = None,
        reason: str = "manual_rollback"
    ) -> Dict[str, Any]:
        """
        Faz rollback do modelo para uma versão anterior.

        Args:
            model_name: Nome do modelo
            target_version: Versão alvo (default: versão anterior à atual)
            reason: Motivo do rollback

        Returns:
            Dict com resultado do rollback
        """
        try:
            # Busca versões
            versions = await asyncio.to_thread(
                self.client.search_model_versions,
                f"name='{model_name}'"
            )

            if not versions:
                return {
                    'success': False,
                    'error': 'Modelo não encontrado'
                }

            # Ordena por versão
            sorted_versions = sorted(
                versions,
                key=lambda v: int(v.version),
                reverse=True
            )

            # Encontra versão atual em Production
            current_prod = None
            for v in sorted_versions:
                if v.current_stage == 'Production':
                    current_prod = v
                    break

            if not current_prod:
                return {
                    'success': False,
                    'error': 'Nenhuma versão em Production'
                }

            # Determina versão alvo
            if target_version:
                target = next(
                    (v for v in sorted_versions if v.version == target_version),
                    None
                )
            else:
                # Versão anterior
                current_idx = next(
                    (i for i, v in enumerate(sorted_versions)
                     if v.version == current_prod.version),
                    -1
                )
                if current_idx < 0 or current_idx + 1 >= len(sorted_versions):
                    return {
                        'success': False,
                        'error': 'Nenhuma versão anterior disponível'
                    }
                target = sorted_versions[current_idx + 1]

            if not target:
                return {
                    'success': False,
                    'error': f'Versão {target_version} não encontrada'
                }

            # Executa rollback
            # 1. Arquiva versão atual
            await asyncio.to_thread(
                self.client.transition_model_version_stage,
                name=model_name,
                version=current_prod.version,
                stage='Archived',
                archive_existing_versions=False
            )

            # 2. Promove versão alvo
            await asyncio.to_thread(
                self.client.transition_model_version_stage,
                name=model_name,
                version=target.version,
                stage='Production',
                archive_existing_versions=False
            )

            # Limpa cache
            self._model_cache.clear()

            # Log rollback
            rollback_info = {
                'success': True,
                'model_name': model_name,
                'previous_version': current_prod.version,
                'new_version': target.version,
                'reason': reason,
                'timestamp': datetime.utcnow().isoformat()
            }

            self.logger.warning(
                "model_rollback_executed",
                **rollback_info
            )

            # Registra métrica de rollback
            try:
                metrics_obj = _get_metrics()
                metrics_obj.ml_model_rollbacks.labels(
                    model_name=model_name
                ).inc()
            except Exception:
                pass

            return rollback_info

        except Exception as e:
            self.logger.error(
                "rollback_failed",
                model_name=model_name,
                error=str(e)
            )
            return {
                'success': False,
                'error': str(e)
            }

    async def enrich_model_metadata(
        self,
        model_name: str,
        version: str,
        metadata: Dict[str, Any]
    ) -> bool:
        """
        Enriquece metadados de uma versão do modelo.

        Args:
            model_name: Nome do modelo
            version: Versão do modelo
            metadata: Metadados adicionais

        Returns:
            True se sucesso, False caso contrário
        """
        try:
            # Busca versão
            versions = await asyncio.to_thread(
                self.client.search_model_versions,
                f"name='{model_name}' AND version='{version}'"
            )

            if not versions:
                self.logger.warning(
                    "version_not_found_for_enrichment",
                    model_name=model_name,
                    version=version
                )
                return False

            v = versions[0]

            # Adiciona tags ao run
            for key, value in metadata.items():
                await asyncio.to_thread(
                    self.client.set_tag,
                    v.run_id,
                    f"enrichment.{key}",
                    str(value)
                )

            self.logger.info(
                "model_metadata_enriched",
                model_name=model_name,
                version=version,
                keys=list(metadata.keys())
            )

            return True

        except Exception as e:
            self.logger.error(
                "enrich_metadata_failed",
                model_name=model_name,
                version=version,
                error=str(e)
            )
            return False

    async def close(self):
        """
        Limpa recursos do Model Registry.
        """
        self._model_cache.clear()
        self.logger.info("model_registry_closed")
