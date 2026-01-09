#!/usr/bin/env python3
"""
Drift-Triggered Retraining: Monitora drift e dispara retreinamento automatico.

Consulta MongoDB por eventos de drift e executa retreinamento quando:
- drift_detected = True
- drift_score > threshold configurado

Uso:
    python drift_triggered_retraining.py [--check-once] [--dry-run]
"""

import argparse
import asyncio
import logging
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DriftTriggeredRetrainer:
    """Monitora drift e dispara retreinamento automatico."""

    def __init__(self, args):
        """Inicializa retrainer com configuracoes."""
        self.args = args
        self.mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
        self.drift_threshold = float(os.getenv('DRIFT_THRESHOLD', '0.2'))
        self.check_interval_minutes = int(os.getenv('DRIFT_CHECK_INTERVAL_MINUTES', '60'))
        self.training_script_path = Path(__file__).parent / 'train_predictive_models.py'

        self.mongo_client: Optional[AsyncIOMotorClient] = None
        self.db = None

    async def setup(self):
        """Configura conexoes."""
        logger.info("Configurando conexao MongoDB...")
        self.mongo_client = AsyncIOMotorClient(self.mongodb_uri)
        self.db = self.mongo_client.neural_hive
        logger.info("Conexao estabelecida")

    async def cleanup(self):
        """Fecha conexoes."""
        if self.mongo_client:
            self.mongo_client.close()
            logger.info("Conexao MongoDB fechada")

    async def check_drift_events(self) -> List[Dict[str, Any]]:
        """
        Consulta eventos de drift recentes que excedem threshold.

        Returns:
            Lista de eventos de drift significativos
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=6)

        cursor = self.db.drift_monitoring.find({
            'drift_detected': True,
            'drift_score': {'$gt': self.drift_threshold},
            'timestamp': {'$gte': cutoff_time},
            'retraining_triggered': {'$ne': True}  # Nao retriggerar
        }).sort('timestamp', -1).limit(10)

        events = await cursor.to_list(length=10)
        logger.info(
            f"Encontrados {len(events)} eventos de drift significativos "
            f"(threshold: {self.drift_threshold})"
        )

        return events

    async def trigger_retraining(self, drift_event: Dict[str, Any], model_type: str) -> bool:
        """
        Dispara retreinamento para modelo especifico.

        Args:
            drift_event: Evento de drift que disparou retreinamento
            model_type: Tipo de modelo a retreinar

        Returns:
            True se retreinamento bem-sucedido
        """
        logger.info(
            f"Disparando retreinamento para {model_type} "
            f"(drift_score: {drift_event.get('drift_score', 0):.3f})"
        )

        if self.args.dry_run:
            logger.info(f"[DRY-RUN] Comando: python {self.training_script_path} "
                       f"--model-type {model_type} --promote-if-better")
            return True

        try:
            # Executa script de treinamento
            result = subprocess.run(
                [
                    sys.executable,
                    str(self.training_script_path),
                    '--model-type', model_type,
                    '--promote-if-better',
                    '--training-window-days', '90'  # Dados mais recentes
                ],
                capture_output=True,
                text=True,
                timeout=3600  # 1 hora timeout
            )

            if result.returncode == 0:
                logger.info(f"Retreinamento de {model_type} concluido com sucesso")
                logger.debug(f"Stdout: {result.stdout}")

                # Marca evento como processado
                await self._mark_retraining_triggered(drift_event['_id'])

                # Registra evento de retreinamento
                await self._log_retraining_event(drift_event, model_type, success=True)

                return True
            else:
                logger.error(
                    f"Retreinamento de {model_type} falhou: {result.stderr}"
                )
                await self._log_retraining_event(
                    drift_event, model_type, success=False, error=result.stderr
                )
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"Retreinamento de {model_type} excedeu timeout")
            return False
        except Exception as e:
            logger.error(f"Erro ao retreinar {model_type}: {e}")
            return False

    async def _mark_retraining_triggered(self, event_id):
        """Marca evento de drift como processado."""
        await self.db.drift_monitoring.update_one(
            {'_id': event_id},
            {
                '$set': {
                    'retraining_triggered': True,
                    'retraining_triggered_at': datetime.utcnow()
                }
            }
        )

    async def _log_retraining_event(
        self,
        drift_event: Dict[str, Any],
        model_type: str,
        success: bool,
        error: Optional[str] = None
    ):
        """Registra evento de retreinamento no MongoDB."""
        document = {
            'type': 'retraining_event',
            'timestamp': datetime.utcnow(),
            'model_type': model_type,
            'triggered_by_drift_event': drift_event.get('_id'),
            'drift_score': drift_event.get('drift_score'),
            'drifted_features': drift_event.get('drifted_features', []),
            'success': success,
            'error': error
        }

        await self.db.ml_retraining_events.insert_one(document)
        logger.debug(f"Evento de retreinamento registrado: {document}")

    async def _send_drift_alert(self, drift_event: Dict[str, Any]):
        """Envia alerta sobre drift detectado."""
        logger.warning(
            "Drift significativo detectado",
            extra={
                'drift_score': drift_event.get('drift_score'),
                'drifted_features': drift_event.get('drifted_features'),
                'threshold': self.drift_threshold
            }
        )

    def _determine_model_type(self, drift_event: Dict[str, Any]) -> str:
        """
        Determina qual modelo retreinar baseado nas features com drift.

        Args:
            drift_event: Evento de drift

        Returns:
            Tipo de modelo a retreinar
        """
        drifted_features = drift_event.get('drifted_features', [])

        # Heuristicas para determinar modelo
        scheduling_features = {'duration_ms', 'queue_time_ms', 'wait_time', 'estimated_duration'}
        load_features = {'request_rate', 'throughput', 'concurrency', 'load'}
        anomaly_features = {'anomaly_score', 'risk_weight', 'retry_count', 'capabilities'}

        drifted_set = set(drifted_features)

        if drifted_set & anomaly_features:
            return 'anomaly'
        elif drifted_set & load_features:
            return 'load'
        elif drifted_set & scheduling_features:
            return 'scheduling'
        else:
            # Default: retreina detector de anomalias
            return 'anomaly'

    async def check_and_retrain(self) -> int:
        """
        Verifica drift e dispara retreinamento se necessario.

        Returns:
            Numero de modelos retreinados
        """
        logger.info("Iniciando verificacao de drift...")

        # Busca eventos de drift
        drift_events = await self.check_drift_events()

        if not drift_events:
            logger.info("Nenhum drift significativo detectado")
            return 0

        retraining_count = 0
        processed_models = set()

        for event in drift_events:
            # Envia alerta
            await self._send_drift_alert(event)

            # Determina modelo a retreinar
            model_type = self._determine_model_type(event)

            # Evita retreinar mesmo modelo multiplas vezes
            if model_type in processed_models:
                logger.info(f"Modelo {model_type} ja foi retreinado neste ciclo")
                continue

            # Dispara retreinamento
            success = await self.trigger_retraining(event, model_type)

            if success:
                retraining_count += 1
                processed_models.add(model_type)

        logger.info(f"Retreinamento concluido: {retraining_count} modelos atualizados")
        return retraining_count

    async def run_monitoring_loop(self):
        """Executa loop de monitoramento continuo."""
        logger.info(
            f"Iniciando monitoramento de drift "
            f"(intervalo: {self.check_interval_minutes}min, threshold: {self.drift_threshold})"
        )

        while True:
            try:
                await self.check_and_retrain()
            except Exception as e:
                logger.error(f"Erro no ciclo de monitoramento: {e}", exc_info=True)

            # Aguarda proximo ciclo
            await asyncio.sleep(self.check_interval_minutes * 60)


async def main():
    """Funcao principal."""
    parser = argparse.ArgumentParser(
        description="Monitora drift e dispara retreinamento automatico"
    )

    parser.add_argument(
        '--check-once',
        action='store_true',
        help='Executa verificacao uma vez e encerra'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simula retreinamento sem executar'
    )

    args = parser.parse_args()

    retrainer = DriftTriggeredRetrainer(args)

    try:
        await retrainer.setup()

        if args.check_once:
            count = await retrainer.check_and_retrain()
            logger.info(f"Verificacao concluida: {count} modelos retreinados")
            return 0 if count >= 0 else 1
        else:
            await retrainer.run_monitoring_loop()

    except KeyboardInterrupt:
        logger.info("Encerrado pelo usuario")
        return 0
    except Exception as e:
        logger.error(f"Erro fatal: {e}", exc_info=True)
        return 1
    finally:
        await retrainer.cleanup()


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
