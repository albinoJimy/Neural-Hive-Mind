"""RetrainingJob - Auto-Retraining Pipeline para Approval Models."""

import asyncio
import json
import logging
import subprocess
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class RetrainingJob:
    """
    Gerencia pipeline de retreinamento automático para modelos de aprovação.

    Coleta feedbacks, treina novo modelo, valida melhoria,
    registra no MLflow e publica eventos Kafka.
    """

    def __init__(
        self,
        mlflow_client: Any,
        model_repo: Any,
        kafka_producer: Any,
        retrain_threshold: int = 100,
        min_f1_improvement: float = 0.05,
        training_script_path: Optional[str] = None,
    ):
        """
        Inicializa o job de retreinamento.

        Args:
            mlflow_client: Cliente MLflow
            model_repo: Repositório de versões de modelo
            kafka_producer: Producer Kafka para eventos
            retrain_threshold: Mínimo de samples para retreino
            min_f1_improvement: Melhoria mínima de F1 para deploy
            training_script_path: Caminho do script de treino
        """
        self.mlflow_client = mlflow_client
        self.model_repo = model_repo
        self.kafka_producer = kafka_producer
        self.retrain_threshold = retrain_threshold
        self.min_f1_improvement = min_f1_improvement
        self.training_script_path = training_script_path or self._find_training_script()
        self._job_status: Dict[str, Any] = {}
        logger.info(f"RetrainingJob inicializado com threshold={retrain_threshold}")

    def _find_training_script(self) -> str:
        """Encontra script de treino padrão."""
        # Procura scripts de treino em locais comuns
        possible_paths = [
            "/app/ml_pipelines/training/retrain_v8_balanced.py",
            "ml_pipelines/training/retrain_v8_balanced.py",
            "./retrain_v8_balanced.py",
        ]
        for path in possible_paths:
            if Path(path).exists():
                return path
        return "ml_pipelines/training/retrain_v8_balanced.py"

    async def check_threshold(self) -> Dict[str, Any]:
        """
        Verifica se há samples suficientes para retreino.

        Returns:
            Dicionário com status do threshold
        """
        try:
            # Conta samples pendentes (do active learning)
            sample_count = await self._count_pending_samples()

            has_enough = sample_count >= self.retrain_threshold

            result = {
                "has_enough_samples": has_enough,
                "sample_count": sample_count,
                "threshold": self.retrain_threshold,
                "checked_at": datetime.utcnow().isoformat(),
            }

            logger.info(
                f"Threshold check: {sample_count}/{self.retrain_threshold} samples"
            )
            return result

        except Exception as e:
            logger.error(f"Erro ao verificar threshold: {e}")
            return {
                "has_enough_samples": False,
                "error": str(e),
                "checked_at": datetime.utcnow().isoformat(),
            }

    async def _count_pending_samples(self) -> int:
        """Conta samples pendentes para treino."""
        # TODO: Implementar contagem real do MongoDB
        # Por ora, retorna valor mockado
        if hasattr(self.model_repo, "count_pending_samples"):
            return await self.model_repo.count_pending_samples()
        return 0

    async def execute_retraining(
        self, script_args: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Executa script de retreinamento.

        Args:
            script_args: Argumentos adicionais para o script

        Returns:
            Dicionário com resultado do retreino
        """
        job_id = f"retrain-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        started_at = datetime.utcnow()

        self._job_status = {
            "job_id": job_id,
            "status": "running",
            "started_at": started_at,
            "script": self.training_script_path,
        }

        try:
            logger.info(f"Executando retreinamento {job_id}")

            cmd = ["python3", self.training_script_path]
            if script_args:
                cmd.extend(script_args)

            # Executa script com timeout de 30 minutos
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=1800, check=False
            )

            # Parse output para extrair métricas
            metrics = self._parse_training_output(result.stdout)

            self._job_status.update(
                {
                    "status": "completed" if result.returncode == 0 else "failed",
                    "completed_at": datetime.utcnow(),
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "metrics": metrics,
                }
            )

            if result.returncode == 0:
                logger.info(f"Retreinamento {job_id} completado: {metrics}")
                return {
                    "success": True,
                    "job_id": job_id,
                    "version": metrics.get("version", "unknown"),
                    "metrics": metrics,
                }
            else:
                logger.error(f"Retreinamento {job_id} falhou: {result.stderr}")
                return {"success": False, "job_id": job_id, "error": result.stderr}

        except subprocess.TimeoutExpired:
            logger.error(f"Retreinamento {job_id} excedeu timeout")
            self._job_status["status"] = "timeout"
            return {
                "success": False,
                "job_id": job_id,
                "error": "Training timeout after 30 minutes",
            }
        except Exception as e:
            logger.error(f"Erro ao executar retreinamento: {e}")
            self._job_status["status"] = "error"
            return {"success": False, "job_id": job_id, "error": str(e)}

    def _parse_training_output(self, stdout: str) -> Dict[str, float]:
        """Extrai métricas do output do treino."""
        metrics = {}
        try:
            # Procura por padrões como "F1-Score: 0.75"
            for line in stdout.split("\n"):
                if "F1-Score:" in line or "f1_score:" in line:
                    parts = line.split(":")
                    if len(parts) > 1:
                        try:
                            metrics["f1_score"] = float(parts[1].strip())
                        except ValueError:
                            pass
                elif "Accuracy:" in line or "accuracy:" in line:
                    parts = line.split(":")
                    if len(parts) > 1:
                        try:
                            metrics["accuracy"] = float(parts[1].strip())
                        except ValueError:
                            pass
        except Exception as e:
            logger.warning(f"Erro ao parsear output: {e}")

        return metrics

    async def validate_model(self, new_metrics: Dict[str, float]) -> Dict[str, Any]:
        """
        Valida se novo modelo deve ser deployado.

        Args:
            new_metrics: Métricas do novo modelo

        Returns:
            Dicionário com decisão de deploy
        """
        try:
            # Busca modelo atual
            current = await self.model_repo.get_active_model()

            if not current:
                # Primeiro modelo - sempre deployar
                return {
                    "should_deploy": True,
                    "reason": "No baseline model exists",
                    "new_f1": new_metrics.get("f1_score", 0),
                }

            current_f1 = current.get("f1_score", 0.5)
            new_f1 = new_metrics.get("f1_score", 0.5)

            f1_improvement = new_f1 - current_f1

            should_deploy = f1_improvement >= self.min_f1_improvement

            result = {
                "should_deploy": should_deploy,
                "current_f1": current_f1,
                "new_f1": new_f1,
                "f1_improvement": f1_improvement,
                "min_improvement": self.min_f1_improvement,
            }

            logger.info(
                f"Validação: F1 {current_f1:.3f} -> {new_f1:.3f} ({f1_improvement:+.3f})"
            )
            return result

        except Exception as e:
            logger.error(f"Erro ao validar modelo: {e}")
            return {"should_deploy": False, "error": str(e)}

    async def register_to_mlflow(
        self,
        model: Any,
        version: str,
        metrics: Dict[str, float],
        params: Dict[str, Any],
        feature_importance: Optional[Dict[str, float]] = None,
        n_samples: int = 0,
    ) -> Dict[str, Any]:
        """
        Registra modelo no MLflow.

        Args:
            model: Modelo treinado
            version: Versão do modelo
            metrics: Métricas de avaliação
            params: Hiperparâmetros
            feature_importance: Importância das features
            n_samples: Número de amostras

        Returns:
            Dicionário com resultado do registro
        """
        try:
            mlflow_version = self.mlflow_client.log_model(
                model=model,
                version=version,
                metrics=metrics,
                params=params,
                feature_importance=feature_importance,
                n_samples=n_samples,
            )

            logger.info(f"Modelo {version} registrado no MLflow como {mlflow_version}")
            return {
                "success": True,
                "version": version,
                "mlflow_version": mlflow_version,
            }

        except Exception as e:
            logger.error(f"Erro ao registrar no MLflow: {e}")
            return {"success": False, "error": str(e)}

    async def publish_kafka_event(self, event_type: str, **kwargs) -> bool:
        """
        Publica evento no Kafka.

        Args:
            event_type: Tipo do evento
            **kwargs: Dados do evento

        Returns:
            True se publicou com sucesso
        """
        try:
            event = {
                "event_type": event_type,
                "timestamp": datetime.utcnow().isoformat(),
                **kwargs,
            }

            topic = (
                "ml.model_trained"
                if event_type == "model_trained"
                else "ml.model_retraining_failed"
            )

            if self.kafka_producer:
                await self.kafka_producer.produce_and_wait(
                    topic=topic, key=event_type, value=json.dumps(event)
                )
                logger.info(f"Evento {event_type} publicado no Kafka")
                return True
            else:
                logger.warning("Kafka producer não disponível")
                return False

        except Exception as e:
            logger.error(f"Erro ao publicar evento: {e}")
            return False

    async def run_retraining(
        self, model: Optional[Any] = None, force: bool = False
    ) -> Dict[str, Any]:
        """
        Executa pipeline completo de retreinamento.

        Args:
            model: Modelo treinado (se None, tenta carregar do treino)
            force: Força retreino mesmo sem threshold

        Returns:
            Dicionário com resultado completo
        """
        version = f"v{datetime.utcnow().strftime('%Y%m%d-%H%M')}"

        try:
            # 1. Verificar threshold (a menos que force=True)
            if not force:
                threshold_check = await self.check_threshold()
                if not threshold_check.get("has_enough_samples"):
                    return {
                        "success": False,
                        "reason": "Insufficient samples",
                        "threshold_check": threshold_check,
                    }

            # 2. Executar retreinamento
            train_result = await self.execute_retraining()
            if not train_result["success"]:
                await self.publish_kafka_event(
                    "model_retraining_failed",
                    version=version,
                    error=train_result.get("error"),
                )
                return train_result

            metrics = train_result.get("metrics", {})

            # 3. Validar modelo
            validation = await self.validate_model(metrics)
            if not validation["should_deploy"]:
                await self.publish_kafka_event(
                    "model_retraining_failed",
                    version=version,
                    reason="Insufficient improvement",
                )
                return {
                    "success": False,
                    "reason": "Model did not improve enough",
                    "validation": validation,
                }

            # 4. Registrar no MLflow
            if model:
                mlflow_result = await self.register_to_mlflow(
                    model=model, version=version, metrics=metrics, params={}
                )
            else:
                mlflow_result = {"success": True, "version": version}

            # 5. Salvar no MongoDB
            await self.model_repo.create(
                version=version,
                mlflow_run_id=mlflow_result.get("mlflow_run_id", ""),
                stage="staging",
                f1_score=metrics.get("f1_score", 0.0),
                accuracy=metrics.get("accuracy", 0.0),
                precision=metrics.get("precision", 0.0),
                recall=metrics.get("recall", 0.0),
                n_samples=metrics.get("n_samples", 0),
            )

            # 6. Publicar evento
            await self.publish_kafka_event(
                "model_trained",
                version=version,
                f1_score=metrics.get("f1_score"),
                deployed=True,
            )

            return {
                "success": True,
                "job_id": train_result.get("job_id"),
                "new_version": version,
                "metrics": metrics,
                "deployed": True,
            }

        except Exception as e:
            logger.error(f"Erro no pipeline de retreinamento: {e}")
            await self.publish_kafka_event(
                "model_retraining_failed", version=version, error=str(e)
            )
            return {"success": False, "error": str(e)}

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtém status de job de retreinamento.

        Args:
            job_id: ID do job

        Returns:
            Dicionário com status ou None
        """
        if self._job_status.get("job_id") == job_id:
            return self._job_status
        return None
