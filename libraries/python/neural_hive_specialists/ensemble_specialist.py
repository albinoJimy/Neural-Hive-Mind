"""
EnsembleSpecialist: Especialista que usa ensemble de múltiplos modelos ML.

Este módulo implementa um especialista que combina predições de múltiplos modelos
ML usando diferentes métodos de agregação (média ponderada, votação, stacking).
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
from opentelemetry import trace

from .base_specialist import BaseSpecialist
from .config import SpecialistConfig

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class EnsembleSpecialist(BaseSpecialist):
    """
    Especialista que usa ensemble de múltiplos modelos ML.

    Carrega múltiplos modelos do MLflow e combina suas predições usando
    pesos configuráveis e métodos de agregação.

    Atributos:
        models (Dict[str, Any]): Dicionário de modelos carregados {nome: modelo}
        ensemble_weights (Dict[str, float]): Pesos para cada modelo
        meta_model (Optional[Any]): Meta-modelo para stacking (se aplicável)
    """

    def __init__(self, config: SpecialistConfig):
        """
        Inicializa EnsembleSpecialist.

        Args:
            config: Configuração do especialista com parâmetros de ensemble
        """
        super().__init__(config)
        self.models: Dict[str, Any] = {}
        self.ensemble_weights: Dict[str, float] = {}
        self.meta_model: Optional[Any] = None

    def _load_model(self) -> Optional[Any]:
        """
        Carrega múltiplos modelos do MLflow para ensemble.

        Carrega cada modelo configurado em ensemble_models e calcula/carrega
        os pesos de ensemble baseado em ensemble_weights_source.

        Returns:
            Dict de modelos carregados (para compatibilidade, retorna primeiro modelo)

        Raises:
            Exception: Se nenhum modelo puder ser carregado
        """
        if not self.config.enable_ensemble:
            logger.warning("Ensemble não habilitado, usando modelo único")
            return super()._load_model()

        if not self.config.ensemble_models:
            logger.error("ensemble_models vazio, não é possível criar ensemble")
            return super()._load_model()

        logger.info(
            "Carregando modelos para ensemble",
            models=self.config.ensemble_models,
            stages=self.config.ensemble_stages,
        )

        # Carregar cada modelo
        # Permitir broadcasting: se ensemble_stages tem 1 item, usar para todos os modelos
        stages = self.config.ensemble_stages
        if len(stages) == 1:
            stages = stages * len(self.config.ensemble_models)

        loaded_models = {}
        for i, model_name in enumerate(self.config.ensemble_models):
            stage = stages[i] if i < len(stages) else "Production"

            try:
                with tracer.start_as_current_span("ensemble.load_model") as span:
                    span.set_attribute("model_name", model_name)
                    span.set_attribute("stage", stage)

                    model = self.mlflow_client.load_model(model_name, stage)
                    if model:
                        loaded_models[model_name] = model
                        logger.info(
                            "Modelo carregado com sucesso",
                            model_name=model_name,
                            stage=stage,
                        )
                    else:
                        logger.warning(
                            "Falha ao carregar modelo",
                            model_name=model_name,
                            stage=stage,
                        )
            except Exception as e:
                logger.error(
                    "Erro ao carregar modelo para ensemble",
                    model_name=model_name,
                    stage=stage,
                    error=str(e),
                )

        if not loaded_models:
            logger.error("Nenhum modelo carregado, fazendo fallback para modelo único")
            return super()._load_model()

        self.models = loaded_models
        logger.info(
            "Modelos carregados para ensemble",
            count=len(loaded_models),
            models=list(loaded_models.keys()),
        )

        # Carregar pesos de ensemble
        self.ensemble_weights = self._load_ensemble_weights()

        # Publicar pesos nas métricas Prometheus
        for model_name, weight in self.ensemble_weights.items():
            self.metrics.set_ensemble_weight(model_name, weight)
            logger.debug(
                "Peso de ensemble publicado nas métricas",
                model_name=model_name,
                weight=weight,
            )

        # Carregar meta-modelo se necessário
        if self.config.ensemble_aggregation_method == "stacking":
            self._load_meta_model()

        # Retornar primeiro modelo para compatibilidade com BaseSpecialist
        return next(iter(self.models.values()))

    def _load_ensemble_weights(self) -> Dict[str, float]:
        """
        Carrega pesos de ensemble baseado em ensemble_weights_source.

        Returns:
            Dict de pesos {model_name: weight}
        """
        weights_source = self.config.ensemble_weights_source

        with tracer.start_as_current_span("ensemble.load_weights") as span:
            span.set_attribute("weights_source", weights_source)

            if weights_source == "config":
                return self._load_weights_from_config()
            elif weights_source == "mlflow_artifact":
                return self._load_weights_from_mlflow_artifact()
            elif weights_source == "learned":
                return self._load_weights_from_meta_model()
            else:
                logger.warning(
                    "weights_source desconhecido, usando pesos iguais",
                    weights_source=weights_source,
                )
                return self._get_equal_weights()

    def _load_weights_from_config(self) -> Dict[str, float]:
        """Carrega pesos da configuração."""
        if self.config.ensemble_weights:
            # Pesos explícitos fornecidos
            weights = {}
            for i, model_name in enumerate(self.models.keys()):
                if i < len(self.config.ensemble_weights):
                    weights[model_name] = self.config.ensemble_weights[i]
                else:
                    logger.warning(
                        "Peso não fornecido para modelo, usando 0",
                        model_name=model_name,
                    )
                    weights[model_name] = 0.0

            # Ajustar pesos para modelos que falharam no carregamento
            weights = self._redistribute_weights_for_missing_models(weights)

            logger.info("Pesos carregados da configuração", weights=weights)
            return weights
        else:
            # Usar pesos iguais
            return self._get_equal_weights()

    def _load_weights_from_mlflow_artifact(self) -> Dict[str, float]:
        """Carrega pesos de artifact do MLflow."""
        try:
            # Usar primeiro modelo como referência para pegar artifact
            first_model_name = list(self.models.keys())[0]
            first_stage = (
                self.config.ensemble_stages[0]
                if self.config.ensemble_stages
                else "Production"
            )

            logger.info(
                "Carregando pesos de ensemble de MLflow artifact",
                model=first_model_name,
                stage=first_stage,
            )

            # Obter metadados do modelo incluindo run_id
            model_metadata = self.mlflow_client.get_model_metadata(
                first_model_name, first_stage
            )
            run_id = model_metadata.get("run_id")

            if not run_id:
                logger.warning(
                    "run_id não encontrado nos metadados do modelo, usando pesos iguais",
                    model=first_model_name,
                )
                return self._get_equal_weights()

            # Baixar artifact ensemble_weights.json
            import tempfile
            import os

            with tempfile.TemporaryDirectory() as tmpdir:
                # Baixar artifact do MLflow
                artifact_path = "ensemble_weights.json"
                try:
                    local_path = self.mlflow_client.client.download_artifacts(
                        run_id=run_id, path=artifact_path, dst_path=tmpdir
                    )

                    weights_file = (
                        os.path.join(local_path, artifact_path)
                        if os.path.isdir(local_path)
                        else local_path
                    )

                    # Ler e parsear JSON
                    with open(weights_file, "r") as f:
                        weights_data = json.load(f)

                    # Validar formato
                    if not isinstance(weights_data, dict):
                        logger.error(
                            "Formato de weights inválido, esperado dict",
                            type=type(weights_data).__name__,
                        )
                        return self._get_equal_weights()

                    # Validar que todos os modelos têm pesos
                    loaded_weights = {}
                    for model_name in self.models.keys():
                        if model_name in weights_data:
                            loaded_weights[model_name] = float(weights_data[model_name])
                        else:
                            logger.warning(
                                "Peso não encontrado para modelo no artifact",
                                model=model_name,
                            )
                            loaded_weights[model_name] = 0.0

                    # Validar que soma está próxima de 1.0
                    total_weight = sum(loaded_weights.values())
                    if abs(total_weight - 1.0) > 0.01:
                        logger.warning(
                            "Soma dos pesos não é 1.0, normalizando", total=total_weight
                        )
                        # Normalizar
                        if total_weight > 0:
                            loaded_weights = {
                                k: v / total_weight for k, v in loaded_weights.items()
                            }

                    logger.info(
                        "Pesos carregados de MLflow artifact",
                        weights=loaded_weights,
                        run_id=run_id,
                    )

                    # Publicar nas métricas
                    for model_name, weight in loaded_weights.items():
                        self.metrics.set_ensemble_weight(model_name, weight)

                    return loaded_weights

                except Exception as artifact_error:
                    logger.warning(
                        "Artifact ensemble_weights.json não encontrado ou erro ao baixar",
                        run_id=run_id,
                        error=str(artifact_error),
                    )
                    return self._get_equal_weights()

        except Exception as e:
            logger.error(
                "Erro ao carregar pesos de MLflow artifact", error=str(e), exc_info=True
            )
            return self._get_equal_weights()

    def _load_weights_from_meta_model(self) -> Dict[str, float]:
        """Extrai pesos dos coeficientes do meta-modelo."""
        if not self.meta_model:
            logger.warning("Meta-modelo não carregado, usando pesos iguais")
            return self._get_equal_weights()

        try:
            # Assumir que meta-modelo é sklearn LogisticRegression ou similar
            if hasattr(self.meta_model, "coef_"):
                coefs = self.meta_model.coef_[0]
                # Normalizar coeficientes para somarem 1.0
                normalized_coefs = np.abs(coefs) / np.sum(np.abs(coefs))

                weights = {}
                for i, model_name in enumerate(self.models.keys()):
                    if i < len(normalized_coefs):
                        weights[model_name] = float(normalized_coefs[i])
                    else:
                        weights[model_name] = 0.0

                logger.info("Pesos extraídos do meta-modelo", weights=weights)
                return weights
            else:
                logger.warning("Meta-modelo não tem coeficientes, usando pesos iguais")
                return self._get_equal_weights()

        except Exception as e:
            logger.error("Erro ao extrair pesos do meta-modelo", error=str(e))
            return self._get_equal_weights()

    def _get_equal_weights(self) -> Dict[str, float]:
        """Retorna pesos iguais para todos os modelos."""
        n_models = len(self.models)
        if n_models == 0:
            return {}

        equal_weight = 1.0 / n_models
        weights = {model_name: equal_weight for model_name in self.models.keys()}

        logger.info("Usando pesos iguais para ensemble", weights=weights)
        return weights

    def _redistribute_weights_for_missing_models(
        self, weights: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Redistribui pesos quando alguns modelos falharam no carregamento.

        Args:
            weights: Pesos originais (incluindo modelos não carregados)

        Returns:
            Pesos redistribuídos apenas para modelos carregados
        """
        # Filtrar apenas modelos carregados
        loaded_weights = {
            model_name: weight
            for model_name, weight in weights.items()
            if model_name in self.models
        }

        if not loaded_weights:
            return self._get_equal_weights()

        # Normalizar para somar 1.0
        total = sum(loaded_weights.values())
        if total > 0:
            normalized_weights = {
                model_name: weight / total
                for model_name, weight in loaded_weights.items()
            }
        else:
            normalized_weights = self._get_equal_weights()

        if len(normalized_weights) != len(weights):
            logger.warning(
                "Pesos redistribuídos devido a modelos não carregados",
                original_count=len(weights),
                loaded_count=len(normalized_weights),
                normalized_weights=normalized_weights,
            )

            # Atualizar métricas Prometheus com pesos redistribuídos
            for model_name, weight in normalized_weights.items():
                self.metrics.set_ensemble_weight(model_name, weight)

        return normalized_weights

    def _load_meta_model(self) -> None:
        """Carrega meta-modelo para stacking."""
        if not self.config.ensemble_meta_model_name:
            logger.warning(
                "ensemble_meta_model_name não configurado, stacking não disponível"
            )
            return

        try:
            meta_model_name = self.config.ensemble_meta_model_name
            stage = "Production"  # Usar Production stage para meta-modelo

            logger.info(
                "Carregando meta-modelo para stacking", meta_model_name=meta_model_name
            )

            self.meta_model = self.mlflow_client.load_model(meta_model_name, stage)

            if self.meta_model:
                logger.info("Meta-modelo carregado com sucesso")
            else:
                logger.warning("Falha ao carregar meta-modelo")

        except Exception as e:
            logger.error("Erro ao carregar meta-modelo", error=str(e))

    def _predict_with_model(self, cognitive_plan: dict) -> Optional[dict]:
        """
        Executa predição com ensemble de modelos.

        Executa inferência em paralelo em todos os modelos e combina
        predições usando método de agregação configurado.

        Args:
            cognitive_plan: Plano cognitivo para avaliar

        Returns:
            Resultado agregado com metadados de ensemble
        """
        if not self.models:
            logger.warning("Nenhum modelo carregado para ensemble")
            return None

        with tracer.start_as_current_span("ensemble.predict") as span:
            span.set_attribute("ensemble.num_models", len(self.models))
            span.set_attribute(
                "ensemble.aggregation_method", self.config.ensemble_aggregation_method
            )

            # Executar predições em paralelo
            predictions = self._execute_parallel_predictions(cognitive_plan)

            if not predictions:
                logger.error("Todas as predições falharam")
                return None

            # Registrar variância entre predições
            variance = self._calculate_prediction_variance(predictions)
            self.metrics.observe_ensemble_variance(variance)

            # Combinar predições
            aggregated_result = self._combine_predictions(predictions)

            if not aggregated_result:
                logger.error("Falha ao combinar predições")
                return None

            # Adicionar metadados de ensemble
            aggregated_result["metadata"] = aggregated_result.get("metadata", {})
            aggregated_result["metadata"].update(
                {
                    "ensemble_models": list(predictions.keys()),
                    "ensemble_weights": self.ensemble_weights,
                    "ensemble_predictions": {
                        model_name: {
                            "confidence": pred.get("confidence_score"),
                            "risk": pred.get("risk_score"),
                            "recommendation": pred.get("recommendation"),
                        }
                        for model_name, pred in predictions.items()
                    },
                    "ensemble_method": self.config.ensemble_aggregation_method,
                    "ensemble_variance": variance,
                }
            )

            # Adicionar ensemble-aware explainability
            self._add_ensemble_explainability(aggregated_result, predictions)

            # Registrar métrica de predição de ensemble
            self.metrics.increment_ensemble_prediction()

            logger.info(
                "Predição de ensemble concluída",
                num_models=len(predictions),
                variance=variance,
                aggregated_confidence=aggregated_result.get("confidence_score"),
            )

            return aggregated_result

    def _execute_parallel_predictions(self, cognitive_plan: dict) -> Dict[str, dict]:
        """
        Executa predições em paralelo em todos os modelos.

        Args:
            cognitive_plan: Plano cognitivo para avaliar

        Returns:
            Dict de predições {model_name: prediction_result}
        """
        predictions = {}

        with ThreadPoolExecutor(max_workers=len(self.models)) as executor:
            future_to_model = {
                executor.submit(
                    self._predict_with_single_model, model_name, model, cognitive_plan
                ): model_name
                for model_name, model in self.models.items()
            }

            # Converter timeout de ms para segundos
            timeout_seconds = self.config.model_inference_timeout_ms / 1000.0

            for future in as_completed(future_to_model):
                model_name = future_to_model[future]
                try:
                    result = future.result(timeout=timeout_seconds)
                    if result:
                        predictions[model_name] = result
                except Exception as e:
                    logger.error(
                        "Erro na predição de modelo individual",
                        model_name=model_name,
                        error=str(e),
                    )
                    self.metrics.increment_ensemble_model_failure(model_name)

        return predictions

    def _predict_with_single_model(
        self, model_name: str, model: Any, cognitive_plan: dict
    ) -> Optional[dict]:
        """
        Executa predição com modelo individual.

        Args:
            model_name: Nome do modelo
            model: Instância do modelo
            cognitive_plan: Plano cognitivo para avaliar

        Returns:
            Resultado da predição ou None se falhou
        """
        import time

        start_time = time.time()

        try:
            with tracer.start_as_current_span("ensemble.model_inference") as span:
                span.set_attribute("model_name", model_name)

                # Reusar o pipeline de inferência do BaseSpecialist
                original_model = self.model
                try:
                    self.model = model
                    result = super()._predict_with_model(cognitive_plan)
                finally:
                    self.model = original_model

                # Registrar duração independente do resultado
                duration = time.time() - start_time
                self.metrics.observe_ensemble_model_duration(model_name, duration)

                # Verificar se result é None ou avaliado como falso antes de acessar campos
                if result is None or not result:
                    logger.warning(
                        "Ensemble model returned no prediction",
                        model_name=model_name,
                        plan_id=cognitive_plan.get("plan_id", "unknown"),
                        duration_seconds=duration,
                    )
                    return None

                # Só extrair metadata se result for um dicionário válido
                prediction_method = result.get("metadata", {}).get(
                    "prediction_method", "unknown"
                )
                calibrated = result.get("calibrated", False)
                confidence_score = result.get("confidence_score", 0.5)
                plan_id = cognitive_plan.get("plan_id", "unknown")
                model_version = result.get("metadata", {}).get(
                    "model_version", "unknown"
                )

                # Log estruturado baseado no método de predição usado
                if prediction_method == "predict_proba":
                    logger.info(
                        "Ensemble model used probabilistic prediction",
                        model_name=model_name,
                        prediction_method=prediction_method,
                        calibrated=calibrated,
                        confidence_score=confidence_score,
                        plan_id=plan_id,
                        model_version=model_version,
                        model_type=type(model).__name__,
                    )
                elif prediction_method in ("predict", "predict_fallback"):
                    logger.warning(
                        "Ensemble model used non-probabilistic prediction",
                        model_name=model_name,
                        prediction_method=prediction_method,
                        calibrated=calibrated,
                        confidence_score=confidence_score,
                        plan_id=plan_id,
                        model_version=model_version,
                        model_type=type(model).__name__,
                    )

                return result

        except Exception as e:
            # Registrar duração mesmo em caso de erro
            duration = time.time() - start_time
            self.metrics.observe_ensemble_model_duration(model_name, duration)

            logger.error(
                "Erro na predição com modelo individual",
                model_name=model_name,
                error=str(e),
                duration_seconds=duration,
            )
            return None

    def _add_ensemble_explainability(
        self, aggregated_result: dict, predictions: Dict[str, dict]
    ) -> None:
        """
        Adiciona explainability ensemble-aware ao resultado agregado.

        Combina feature importances de múltiplos modelos ponderadas pelos pesos do ensemble.
        Inclui informações sobre calibração dos modelos.

        Args:
            aggregated_result: Resultado agregado a ser enriquecido
            predictions: Predições individuais dos modelos
        """
        try:
            # Verificar se algum modelo tem explainability
            explainability_data = []
            for model_name, pred in predictions.items():
                if "explainability" in pred and pred["explainability"]:
                    explainability_data.append((model_name, pred["explainability"]))

            # Coletar informações de calibração de todos os modelos
            calibrated_models = [
                model_name
                for model_name, pred in predictions.items()
                if pred.get("calibrated", False)
            ]
            non_calibrated_models = [
                model_name
                for model_name, pred in predictions.items()
                if not pred.get("calibrated", False)
            ]
            prediction_methods = {
                model_name: pred.get("metadata", {}).get("prediction_method", "unknown")
                for model_name, pred in predictions.items()
            }
            calibration_coverage = (
                len(calibrated_models) / len(predictions) if predictions else 0.0
            )

            # Log se há mistura de modelos calibrados e não-calibrados
            if calibrated_models and non_calibrated_models:
                logger.warning(
                    "Ensemble com mistura de modelos calibrados e nao-calibrados pode afetar interpretabilidade",
                    calibrated_models=calibrated_models,
                    non_calibrated_models=non_calibrated_models,
                    calibration_coverage=calibration_coverage,
                )

            # Agregar feature importances ponderadas (se houver dados de explainability)
            aggregated_importances = {}
            if explainability_data:
                for model_name, expl in explainability_data:
                    weight = self.ensemble_weights.get(model_name, 0.0)

                    # Processar feature importances se disponíveis
                    if "feature_importances" in expl:
                        for feature_name, importance in expl[
                            "feature_importances"
                        ].items():
                            if feature_name not in aggregated_importances:
                                aggregated_importances[feature_name] = 0.0
                            aggregated_importances[feature_name] += importance * weight

            # Criar estrutura de explainability agregada
            ensemble_explainability = {
                "ensemble": {
                    "aggregated_feature_importances": aggregated_importances,
                    "models_contributing": [
                        model_name for model_name, _ in explainability_data
                    ],
                    "individual_explainabilities": {
                        model_name: {
                            "feature_importances": expl.get("feature_importances", {}),
                            "method": expl.get("method", "unknown"),
                        }
                        for model_name, expl in explainability_data
                    },
                    "calibration_info": {
                        "calibrated_models": calibrated_models,
                        "non_calibrated_models": non_calibrated_models,
                        "calibration_coverage": calibration_coverage,
                        "prediction_methods": prediction_methods,
                    },
                }
            }

            # Adicionar ao resultado agregado
            if "explainability" not in aggregated_result:
                aggregated_result["explainability"] = {}

            aggregated_result["explainability"].update(ensemble_explainability)

            # Anotar metadata adicional
            if "metadata" not in aggregated_result:
                aggregated_result["metadata"] = {}

            aggregated_result["metadata"][
                "ensemble_explainability_source"
            ] = "aggregated_from_base_models"
            aggregated_result["metadata"]["ensemble_explainability_models"] = [
                model_name for model_name, _ in explainability_data
            ]

            logger.debug(
                "Ensemble explainability adicionada",
                num_models_with_explainability=len(explainability_data),
                num_features=len(aggregated_importances),
                calibrated_models_count=len(calibrated_models),
                calibration_coverage=calibration_coverage,
            )

        except Exception as e:
            logger.error(
                "Erro ao adicionar ensemble explainability", error=str(e), exc_info=True
            )

    def _calculate_prediction_variance(self, predictions: Dict[str, dict]) -> float:
        """
        Calcula variância entre predições dos modelos.

        Args:
            predictions: Dict de predições dos modelos

        Returns:
            Variância (desvio padrão) dos confidence scores
        """
        if not predictions:
            return 0.0

        confidence_scores = [
            pred.get("confidence_score", 0.5) for pred in predictions.values()
        ]

        if len(confidence_scores) < 2:
            return 0.0

        return float(np.std(confidence_scores))

    def _combine_predictions(self, predictions: Dict[str, dict]) -> Optional[dict]:
        """
        Combina predições usando método de agregação configurado.

        Args:
            predictions: Dict de predições {model_name: prediction}

        Returns:
            Resultado agregado com metadata de calibração propagada
        """
        method = self.config.ensemble_aggregation_method

        with tracer.start_as_current_span("ensemble.combine_predictions") as span:
            span.set_attribute("aggregation_method", method)

            if method == "weighted_average":
                result = self._weighted_average_aggregation(predictions)
            elif method == "voting":
                result = self._voting_aggregation(predictions)
            elif method == "stacking":
                result = self._stacking_aggregation(predictions)
            else:
                logger.warning(
                    "Método de agregação desconhecido, usando weighted_average",
                    method=method,
                )
                result = self._weighted_average_aggregation(predictions)

            # Propagar metadata de calibração dos modelos base
            if result is not None:
                # Coletar métodos de predição de cada modelo
                base_models_prediction_methods = {
                    model_name: pred.get("metadata", {}).get(
                        "prediction_method", "unknown"
                    )
                    for model_name, pred in predictions.items()
                }

                # Contar modelos calibrados
                calibrated_count = sum(
                    1 for pred in predictions.values() if pred.get("calibrated", False)
                )
                total_models = len(predictions)
                calibration_coverage = (
                    calibrated_count / total_models if total_models > 0 else 0.0
                )

                # Inicializar metadata se não existir
                if "metadata" not in result:
                    result["metadata"] = {}

                # Adicionar metadata de calibração agregada
                result["metadata"][
                    "base_models_prediction_methods"
                ] = base_models_prediction_methods
                result["metadata"]["calibrated_models_count"] = calibrated_count
                result["metadata"]["ensemble_calibrated"] = (
                    calibrated_count > total_models / 2
                )
                result["metadata"]["calibration_coverage"] = calibration_coverage
                result["metadata"]["aggregation_method"] = method

                # Registrar métricas de calibração
                self.metrics.observe_ensemble_calibration_coverage(calibration_coverage)
                self.metrics.increment_ensemble_probabilistic_prediction(
                    method, calibrated_count > total_models / 2
                )

            return result

    def _weighted_average_aggregation(self, predictions: Dict[str, dict]) -> dict:
        """
        Agrega predições usando média ponderada.

        Args:
            predictions: Dict de predições

        Returns:
            Resultado agregado
        """
        # Calcular média ponderada de confidence e risk scores
        weighted_confidence = 0.0
        weighted_risk = 0.0
        total_weight = 0.0

        for model_name, pred in predictions.items():
            weight = self.ensemble_weights.get(model_name, 0.0)
            weighted_confidence += pred.get("confidence_score", 0.5) * weight
            weighted_risk += pred.get("risk_score", 0.5) * weight
            total_weight += weight

        # Normalizar se pesos não somam 1.0
        if total_weight > 0:
            weighted_confidence /= total_weight
            weighted_risk /= total_weight

        # Validar complementaridade quando todos modelos usam predict_proba
        calibrated_models = sum(
            1 for pred in predictions.values() if pred.get("calibrated", False)
        )
        num_models = len(predictions)

        if calibrated_models == num_models and num_models > 0:
            # Todos modelos calibrados - validar complementaridade
            score_sum = weighted_confidence + weighted_risk
            if abs(score_sum - 1.0) > 0.05:
                logger.warning(
                    "Weighted scores not complementary despite all calibrated models",
                    weighted_confidence=weighted_confidence,
                    weighted_risk=weighted_risk,
                    sum=score_sum,
                    calibrated_models=calibrated_models,
                    num_models=num_models,
                )

        # Logging estruturado após agregação
        logger.info(
            "Weighted average aggregation completed",
            weighted_confidence=weighted_confidence,
            weighted_risk=weighted_risk,
            num_models=num_models,
            calibrated_models=calibrated_models,
            aggregation_method="weighted_average",
        )

        # Determinar recomendação baseada em confidence agregado
        if weighted_confidence >= self.config.ensemble_approve_threshold:
            recommendation = "approve"
        elif weighted_confidence >= self.config.ensemble_review_threshold:
            recommendation = "review_required"
        else:
            recommendation = "reject"

        # Agregar reasoning factors (união de todos)
        all_reasoning_factors = []
        for pred in predictions.values():
            all_reasoning_factors.extend(pred.get("reasoning_factors", []))

        # Remover duplicatas mantendo ordem
        unique_reasoning = []
        seen = set()
        for factor in all_reasoning_factors:
            factor_key = factor.get("factor", "")
            if factor_key not in seen:
                seen.add(factor_key)
                unique_reasoning.append(factor)

        return {
            "confidence_score": float(weighted_confidence),
            "risk_score": float(weighted_risk),
            "recommendation": recommendation,
            "reasoning_summary": f"Avaliação baseada em ensemble de {len(predictions)} modelos",
            "reasoning_factors": unique_reasoning[:10],  # Limitar a 10 fatores
            "mitigations": [],
        }

    def _voting_aggregation(self, predictions: Dict[str, dict]) -> dict:
        """
        Agrega predições usando votação majoritária.

        Args:
            predictions: Dict de predições

        Returns:
            Resultado agregado
        """
        # Contar votos para cada recomendação
        votes = {}
        for model_name, pred in predictions.items():
            recommendation = pred.get("recommendation", "review_required")
            weight = self.ensemble_weights.get(model_name, 1.0)
            votes[recommendation] = votes.get(recommendation, 0.0) + weight

        # Determinar vencedor
        winning_recommendation = max(votes.items(), key=lambda x: x[1])[0]

        # Calcular confidence baseado na força da maioria
        total_votes = sum(votes.values())
        majority_strength = (
            votes[winning_recommendation] / total_votes if total_votes > 0 else 0.5
        )

        # Pegar predição de um modelo que votou na recomendação vencedora
        winning_pred = next(
            pred
            for pred in predictions.values()
            if pred.get("recommendation") == winning_recommendation
        )

        result = winning_pred.copy()
        result["confidence_score"] = float(majority_strength)
        result["reasoning_summary"] = (
            f"Votação: {winning_recommendation} "
            f"({votes[winning_recommendation]:.1f}/{total_votes:.1f} votos)"
        )

        return result

    def _stacking_aggregation(self, predictions: Dict[str, dict]) -> dict:
        """
        Agrega predições usando meta-modelo (stacking).

        Args:
            predictions: Dict de predições

        Returns:
            Resultado agregado com metadata de calibração
        """
        if not self.meta_model:
            logger.warning("Meta-modelo não disponível, usando weighted_average")
            return self._weighted_average_aggregation(predictions)

        try:
            # Preparar features para meta-modelo (predições dos modelos base)
            base_predictions = []
            for model_name in sorted(self.models.keys()):
                if model_name in predictions:
                    pred = predictions[model_name]
                    base_predictions.extend(
                        [pred.get("confidence_score", 0.5), pred.get("risk_score", 0.5)]
                    )

            # Executar meta-modelo
            meta_features = np.array(base_predictions).reshape(1, -1)

            # Coletar informações sobre modelos base calibrados
            base_models_calibrated = [
                model_name
                for model_name, pred in predictions.items()
                if pred.get("calibrated", False)
            ]

            # Tentar usar predict_proba para modelos de classificação
            meta_model_method = "unknown"
            meta_model_calibrated = False

            try:
                if hasattr(self.meta_model, "predict_proba"):
                    # Usar predict_proba para obter probabilidades
                    probas = self.meta_model.predict_proba(meta_features)[0]
                    # Assumir que a segunda coluna é a probabilidade da classe positiva
                    confidence = (
                        float(probas[1]) if len(probas) > 1 else float(probas[0])
                    )
                    risk = 1.0 - confidence
                    meta_model_method = "predict_proba"
                    meta_model_calibrated = True

                    logger.info(
                        "Meta-model used probabilistic prediction for stacking",
                        meta_model_method=meta_model_method,
                        confidence=confidence,
                        num_base_predictions=len(predictions),
                        base_models_calibrated_count=len(base_models_calibrated),
                    )

                elif hasattr(self.meta_model, "decision_function"):
                    # Usar decision_function e escalar para [0,1]
                    decision_score = self.meta_model.decision_function(meta_features)[0]
                    # Aplicar sigmoid para converter para probabilidade
                    confidence = float(1.0 / (1.0 + np.exp(-decision_score)))
                    risk = 1.0 - confidence
                    meta_model_method = "decision_function"
                    meta_model_calibrated = False

                    logger.warning(
                        "Meta-model used decision_function fallback for stacking",
                        meta_model_method=meta_model_method,
                        decision_score=decision_score,
                        confidence=confidence,
                        num_base_predictions=len(predictions),
                    )

                else:
                    # Fallback para predict
                    meta_prediction = self.meta_model.predict(meta_features)[0]
                    meta_model_method = "predict"
                    meta_model_calibrated = False

                    # Converter predição do meta-modelo para formato padrão
                    if isinstance(meta_prediction, (list, np.ndarray)):
                        confidence = float(meta_prediction[0])
                        risk = (
                            float(meta_prediction[1])
                            if len(meta_prediction) > 1
                            else 1.0 - confidence
                        )
                    else:
                        confidence = float(meta_prediction)
                        risk = 1.0 - confidence

                    logger.warning(
                        "Meta-model used predict fallback for stacking",
                        meta_model_method=meta_model_method,
                        confidence=confidence,
                        num_base_predictions=len(predictions),
                    )

            except Exception as e:
                logger.error(
                    "Erro ao executar meta-modelo, usando fallback", error=str(e)
                )
                # Fallback para predict simples
                meta_prediction = self.meta_model.predict(meta_features)[0]
                confidence = float(meta_prediction)
                risk = 1.0 - confidence
                meta_model_method = "predict_fallback"
                meta_model_calibrated = False

            # Determinar recomendação
            if confidence >= self.config.ensemble_approve_threshold:
                recommendation = "approve"
            elif confidence >= self.config.ensemble_review_threshold:
                recommendation = "review_required"
            else:
                recommendation = "reject"

            return {
                "confidence_score": confidence,
                "risk_score": risk,
                "calibrated": meta_model_calibrated,
                "recommendation": recommendation,
                "reasoning_summary": f"Stacking: meta-modelo combinou {len(predictions)} predições base",
                "reasoning_factors": [],
                "mitigations": [],
                "metadata": {
                    "meta_model_method": meta_model_method,
                    "meta_model_calibrated": meta_model_calibrated,
                    "base_models_calibrated": base_models_calibrated,
                },
            }

        except Exception as e:
            logger.error(
                "Erro no stacking, usando weighted_average como fallback", error=str(e)
            )
            return self._weighted_average_aggregation(predictions)
