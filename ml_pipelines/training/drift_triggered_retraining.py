#!/usr/bin/env python3
"""
Drift-Triggered Retraining: Monitora drift e dispara retreinamento automatico.

Consulta MongoDB por eventos de drift e executa retreinamento quando:
- drift_detected = True
- drift_score > threshold configurado

Integração A/B Testing (Passo 5.7):
- Após retreinamento bem-sucedido, cria teste A/B automático
- Inicia com 10% de tráfego para novo modelo
- Monitora métricas e expande tráfego automaticamente
- Promove para 100% se métricas positivas

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

# Importar A/B testing (Passo 5.7)
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from ab_testing import ABTestManager, ABTestConfig, start_ab_test
    AB_TESTING_AVAILABLE = True
except ImportError:
    AB_TESTING_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("ab_testing_module_not_available")

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

        # A/B Testing Configuration (Passo 5.7)
        self.ab_testing_enabled = os.getenv('AB_TESTING_ENABLED', 'true').lower() == 'true'
        self.ab_manager: Optional[ABTestManager] = None
        if AB_TESTING_AVAILABLE and self.ab_testing_enabled:
            self.ab_manager = ABTestManager()

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

        Integração A/B Testing (Passo 5.7):
        - Após retreinamento bem-sucedido, inicia teste A/B automático
        - Começa com 10% de tráfego para novo modelo
        - Expande gradualmente baseado em métricas

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
            if self.ab_testing_enabled:
                logger.info(f"[DRY-RUN] Criaria teste A/B com 10% de tráfego inicial")
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

                # === PASSO 5.7: Iniciar A/B Testing automático ===
                if self.ab_testing_enabled and self.ab_manager:
                    await self._start_ab_test_after_retraining(model_type, drift_event)

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

    async def _start_ab_test_after_retraining(
        self,
        model_type: str,
        drift_event: Dict[str, Any]
    ):
        """
        Inicia teste A/B após retreinamento bem-sucedido (Passo 5.7).

        Cria teste A/B com:
        - 10% de tráfego inicial para novo modelo
        - Threshold de sucesso: 2% de melhoria
        - Mínimo de 1000 amostras por modelo
        - 72 horas de duração mínima

        Args:
            model_type: Tipo de modelo retreinado
            drift_event: Evento de drift que disparou retreinamento
        """
        if not self.ab_manager:
            return

        try:
            # Mapear model_type para specialist_type
            specialist_type = self._map_model_to_specialist(model_type)

            # Gerar nova versão do modelo (timestamp)
            new_version = f"v{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

            # Criar configuração de teste A/B
            config = ABTestConfig(
                specialist_type=specialist_type,
                new_model_version=new_version,
                baseline_model_version='Production',
                traffic_percentage=10.0,  # Começa com 10%
                min_samples=1000,
                duration_hours=72,
                success_threshold=0.02,  # 2% de melhoria
                confidence_threshold=0.70
            )

            # Criar teste
            test_id = self.ab_manager.create_test(config)

            logger.info(
                "ab_test_created_after_retraining",
                test_id=test_id,
                specialist_type=specialist_type,
                new_version=new_version,
                initial_traffic_percentage=10.0,
                drift_score=drift_event.get('drift_score')
            )

            # Registrar evento de criação de teste A/B
            await self._log_ab_test_event(
                test_id=test_id,
                specialist_type=specialist_type,
                new_version=new_version,
                triggered_by_drift=drift_event.get('_id')
            )

            # Iniciar monitoramento automático de expansão
            asyncio.create_task(
                self._monitor_and_expand_ab_test(test_id, specialist_type)
            )

        except Exception as e:
            logger.error(f"Erro ao criar teste A/B: {e}")

    async def _monitor_and_expand_ab_test(
        self,
        test_id: str,
        specialist_type: str
    ):
        """
        Monitora teste A/B e expande tráfego automaticamente (Passo 5.7).

        Estratégia de Expansão:
        - 10% -> 25%: após 24h se métricas estáveis
        - 25% -> 50%: após 48h se métricas positivas
        - 50% -> 100%: após 72h se teste passou
        - Rollback para 0% se métricas negativas

        Args:
            test_id: ID do teste A/B
            specialist_type: Tipo do especialista
        """
        if not self.ab_manager:
            return

        expansion_schedule = [
            {'hours': 24, 'traffic': 25.0, 'condition': 'stable'},
            {'hours': 48, 'traffic': 50.0, 'condition': 'positive'},
            {'hours': 72, 'traffic': 100.0, 'condition': 'passed'}
        ]

        try:
            start_time = datetime.utcnow()

            for step in expansion_schedule:
                # Aguardar até horário da expansão
                target_time = start_time + timedelta(hours=step['hours'])
                wait_seconds = (target_time - datetime.utcnow()).total_seconds()

                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)

                # Verificar status do teste
                result = self.ab_manager.check_test_completion(test_id)

                # Rollback se falhou
                if result.get('status') == 'failed':
                    logger.warning(
                        "ab_test_failed_rolling_back",
                        test_id=test_id,
                        reason=result.get('recommendation')
                    )
                    self.ab_manager.expand_traffic(test_id, 0.0)
                    await self._log_ab_test_expansion(
                        test_id, 0.0, 'rollback_failed'
                    )
                    return

                # Expandir tráfego se condição atendida
                if step['condition'] == 'passed' and result.get('passed'):
                    self.ab_manager.expand_traffic(test_id, step['traffic'])
                    await self._log_ab_test_expansion(
                        test_id, step['traffic'], 'test_passed'
                    )
                    logger.info(
                        "ab_test_expanded_to_full_traffic",
                        test_id=test_id,
                        traffic_percentage=100.0
                    )
                    return
                elif step['condition'] in ['stable', 'positive']:
                    # Verificar métricas intermediárias
                    metrics = result.get('metrics', {})
                    new_model = metrics.get('new_model', {})
                    baseline_model = metrics.get('baseline_model', {})

                    # Expandir se novo modelo não é pior
                    if new_model.get('confidence_mean', 0) >= baseline_model.get('confidence_mean', 0) * 0.95:
                        self.ab_manager.expand_traffic(test_id, step['traffic'])
                        await self._log_ab_test_expansion(
                            test_id, step['traffic'], step['condition']
                        )
                        logger.info(
                            "ab_test_traffic_expanded",
                            test_id=test_id,
                            new_traffic_percentage=step['traffic'],
                            condition=step['condition']
                        )
                    else:
                        logger.warning(
                            "ab_test_metrics_degraded_not_expanding",
                            test_id=test_id,
                            new_confidence=new_model.get('confidence_mean'),
                            baseline_confidence=baseline_model.get('confidence_mean')
                        )

        except Exception as e:
            logger.error(f"Erro no monitoramento de teste A/B: {e}")

    def _map_model_to_specialist(self, model_type: str) -> str:
        """Mapeia tipo de modelo para specialist_type."""
        mapping = {
            'anomaly': 'behavior',
            'load': 'technical',
            'scheduling': 'evolution',
            'business': 'business',
            'architecture': 'architecture'
        }
        return mapping.get(model_type, model_type)

    async def _log_ab_test_event(
        self,
        test_id: str,
        specialist_type: str,
        new_version: str,
        triggered_by_drift: Any
    ):
        """Registra evento de criação de teste A/B no MongoDB."""
        try:
            document = {
                'type': 'ab_test_created',
                'timestamp': datetime.utcnow(),
                'test_id': test_id,
                'specialist_type': specialist_type,
                'new_model_version': new_version,
                'triggered_by_drift_event': triggered_by_drift,
                'initial_traffic_percentage': 10.0
            }
            await self.db.ml_retraining_events.insert_one(document)
        except Exception as e:
            logger.error(f"Erro ao registrar evento A/B test: {e}")

    async def _log_ab_test_expansion(
        self,
        test_id: str,
        new_traffic: float,
        reason: str
    ):
        """Registra expansão de tráfego de teste A/B."""
        try:
            document = {
                'type': 'ab_test_traffic_expanded',
                'timestamp': datetime.utcnow(),
                'test_id': test_id,
                'new_traffic_percentage': new_traffic,
                'expansion_reason': reason
            }
            await self.db.ml_retraining_events.insert_one(document)
        except Exception as e:
            logger.error(f"Erro ao registrar expansão A/B test: {e}")

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
