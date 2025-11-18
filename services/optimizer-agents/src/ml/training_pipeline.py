"""
Training Pipeline para treinamento periódico de modelos ML.

Orquestra retraining diário de LoadPredictor (Prophet/ARIMA) e
SchedulingOptimizer (Q-learning) usando dados históricos.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)


class TrainingPipeline:
    """
    Pipeline de treinamento periódico para modelos de scheduling.

    Executa:
    - Treinamento diário de modelos Prophet/ARIMA
    - Atualização de políticas Q-learning
    - Validação de qualidade de dados
    - Promoção automática de modelos
    """

    def __init__(
        self,
        load_predictor,
        scheduling_optimizer,
        clickhouse_client,
        mongodb_client,
        model_registry,
        metrics,
        config: Dict
    ):
        """
        Args:
            load_predictor: Instância de LoadPredictor
            scheduling_optimizer: Instância de SchedulingOptimizer
            clickhouse_client: Cliente ClickHouse
            mongodb_client: Cliente MongoDB
            model_registry: Registry MLflow
            metrics: Métricas Prometheus
            config: Configuração
        """
        self.load_predictor = load_predictor
        self.scheduling_optimizer = scheduling_optimizer
        self.clickhouse = clickhouse_client
        self.mongodb = mongodb_client
        self.model_registry = model_registry
        self.metrics = metrics
        self.config = config

        # Configurações de treinamento
        self.training_interval_hours = config.get('ml_training_interval_hours', 24)
        self.training_window_days = config.get('ml_training_window_days', 540)  # 18 meses
        self.min_training_samples = config.get('ml_min_training_samples', 1000)

        # Controle de execução
        self._training_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start_periodic_training(self) -> None:
        """Inicia loop de treinamento periódico em background."""
        if self._training_task and not self._training_task.done():
            logger.warning("Pipeline de treinamento já em execução")
            return

        logger.info(f"Iniciando pipeline de treinamento (intervalo={self.training_interval_hours}h)")

        # Criar tarefa assíncrona
        self._training_task = asyncio.create_task(self._training_loop())

    async def stop_periodic_training(self) -> None:
        """Para loop de treinamento."""
        logger.info("Parando pipeline de treinamento")
        self._stop_event.set()

        if self._training_task:
            await self._training_task
            logger.info("Pipeline de treinamento parado")

    async def _training_loop(self) -> None:
        """Loop principal de treinamento periódico."""
        while not self._stop_event.is_set():
            try:
                # Executar ciclo de treinamento
                await self._run_training_cycle()

                # Aguardar próximo intervalo
                interval_seconds = self.training_interval_hours * 3600
                logger.info(f"Próximo treinamento em {self.training_interval_hours}h")

                # Aguardar com possibilidade de interrupção
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=interval_seconds
                    )
                except asyncio.TimeoutError:
                    continue  # Timeout normal, continuar loop

            except Exception as e:
                logger.error(f"Erro no loop de treinamento: {e}")
                # Aguardar 1 hora antes de tentar novamente
                await asyncio.sleep(3600)

    async def _run_training_cycle(self) -> None:
        """Executa ciclo completo de treinamento."""
        logger.info("=== Iniciando ciclo de treinamento ===")
        start_time = datetime.utcnow()

        results = {}

        try:
            # 1. Treinar LoadPredictor
            logger.info("1/2 - Treinando LoadPredictor")
            load_results = await self.train_load_predictor()
            results['load_predictor'] = load_results

            # 2. Treinar SchedulingOptimizer
            logger.info("2/2 - Treinando SchedulingOptimizer")
            scheduling_results = await self.train_scheduling_optimizer()
            results['scheduling_optimizer'] = scheduling_results

            # Registrar métricas
            duration = (datetime.utcnow() - start_time).total_seconds()
            self.metrics.record_ml_training('training_cycle', duration, results)

            logger.info(f"=== Ciclo de treinamento concluído em {duration:.2f}s ===")

        except Exception as e:
            logger.error(f"Erro no ciclo de treinamento: {e}")
            duration = (datetime.utcnow() - start_time).total_seconds()
            self.metrics.record_ml_training('training_cycle', duration, {'error': str(e)})

    async def train_load_predictor(self) -> Dict:
        """
        Treina modelos de previsão de carga.

        Returns:
            Dict com resultados de treinamento por horizonte
        """
        logger.info(f"Treinando LoadPredictor (janela={self.training_window_days} dias)")
        start_time = datetime.utcnow()

        try:
            # 1. Buscar dados históricos do ClickHouse
            logger.info("Buscando dados históricos do ClickHouse")
            historical_data = await self._fetch_clickhouse_training_data(
                window_days=self.training_window_days
            )

            # 2. Validar qualidade dos dados
            logger.info("Validando qualidade dos dados")
            validation = self._validate_data_quality(historical_data)

            if not validation['is_valid']:
                logger.error(f"Dados inválidos: {validation['issues']}")
                return {
                    'success': False,
                    'error': 'Invalid data quality',
                    'issues': validation['issues']
                }

            # 3. Backfill missing data (interpolação de gaps)
            logger.info("Preenchendo gaps nos dados")
            historical_data = await self._backfill_missing_data(historical_data)

            # 4. Treinar modelo
            logger.info("Treinando modelo Prophet")
            training_results = await self.load_predictor.train_model(
                training_window_days=self.training_window_days
            )

            # 5. Avaliar e promover se necessário
            for horizon, metrics in training_results.items():
                if metrics['mape'] < 20.0:
                    logger.info(f"Modelo {horizon}m aprovado (MAPE={metrics['mape']:.2f}%)")
                else:
                    logger.warning(f"Modelo {horizon}m não aprovado (MAPE={metrics['mape']:.2f}%)")

            duration = (datetime.utcnow() - start_time).total_seconds()

            return {
                'success': True,
                'results': training_results,
                'data_points': len(historical_data),
                'duration_seconds': duration,
            }

        except Exception as e:
            logger.error(f"Erro ao treinar LoadPredictor: {e}")
            # Retry logic
            return await self._retry_training('load_predictor', e)

    async def train_scheduling_optimizer(self) -> Dict:
        """
        Treina política de agendamento via batch Q-learning.

        Coleta state-action-reward tuples do MongoDB e atualiza Q-table.

        Returns:
            Dict com resultados de treinamento
        """
        logger.info("Treinando SchedulingOptimizer")
        start_time = datetime.utcnow()

        try:
            # 1. Buscar histórico de otimizações do MongoDB
            logger.info("Buscando histórico de otimizações do MongoDB")
            optimization_history = await self._fetch_optimization_history(days=30)

            if len(optimization_history) < 100:
                logger.warning(f"Dados insuficientes: {len(optimization_history)} < 100")
                return {
                    'success': False,
                    'error': 'Insufficient optimization history',
                    'data_points': len(optimization_history)
                }

            # 2. Extrair state-action-reward tuples
            logger.info("Extraindo state-action-reward tuples")
            tuples = self._extract_sar_tuples(optimization_history)

            # 3. Batch Q-learning update
            logger.info(f"Atualizando Q-table com {len(tuples)} tuples")
            for state, action, reward, next_state in tuples:
                await self.scheduling_optimizer.update_policy(reward, next_state)

            # 4. Avaliar política via simulação
            logger.info("Avaliando política")
            evaluation = await self._evaluate_policy_simulation(tuples)

            # 5. Salvar snapshot
            logger.info("Salvando snapshot da política")
            await self.scheduling_optimizer._save_q_table_snapshot()

            duration = (datetime.utcnow() - start_time).total_seconds()

            return {
                'success': True,
                'tuples_processed': len(tuples),
                'q_table_size': len(self.scheduling_optimizer.q_table),
                'average_reward': evaluation.get('average_reward', 0),
                'duration_seconds': duration,
            }

        except Exception as e:
            logger.error(f"Erro ao treinar SchedulingOptimizer: {e}")
            return await self._retry_training('scheduling_optimizer', e)

    def _validate_data_quality(self, data: list) -> Dict:
        """
        Valida qualidade dos dados históricos.

        Returns:
            Dict com is_valid e issues
        """
        issues = []

        # Verificar quantidade mínima
        if len(data) < self.min_training_samples:
            issues.append(f"Amostras insuficientes: {len(data)} < {self.min_training_samples}")

        # Verificar campos obrigatórios
        if data:
            required = {'timestamp', 'ticket_count'}
            if not required.issubset(data[0].keys()):
                issues.append(f"Campos faltando: {required - set(data[0].keys())}")

        # Verificar gaps temporais (>10% missing)
        if len(data) > 1:
            timestamps = [d['timestamp'] for d in data]
            expected_intervals = len(data) - 1
            # Calcular gaps
            # (Simplificado: assumir 1 ponto por hora)
            actual_span = (timestamps[-1] - timestamps[0]).total_seconds() / 3600
            gap_percentage = abs(actual_span - expected_intervals) / max(expected_intervals, 1)

            if gap_percentage > 0.1:
                issues.append(f"Gaps temporais excessivos: {gap_percentage*100:.1f}%")

        # Verificar outliers extremos
        if data:
            counts = [d['ticket_count'] for d in data if 'ticket_count' in d]
            if counts:
                median = np.median(counts)
                outliers = sum(1 for c in counts if c > 10 * median)
                if outliers > len(counts) * 0.05:
                    issues.append(f"Muitos outliers: {outliers} ({100*outliers/len(counts):.1f}%)")

        return {
            'is_valid': len(issues) == 0,
            'issues': issues,
            'data_points': len(data),
        }

    async def _backfill_missing_data(self, data: list) -> list:
        """
        Preenche gaps temporais usando interpolação.

        Args:
            data: Lista de dicts com timestamp e valores

        Returns:
            Lista com gaps preenchidos
        """
        if not data or len(data) < 2:
            return data

        # Converter para DataFrame pandas para facilitar interpolação
        import pandas as pd
        df = pd.DataFrame(data)

        if 'timestamp' not in df.columns:
            return data

        # Ordenar por timestamp
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp').reset_index(drop=True)

        # Criar range completo
        full_range = pd.date_range(
            start=df['timestamp'].min(),
            end=df['timestamp'].max(),
            freq='H'  # 1 hora
        )

        # Reindexar
        df = df.set_index('timestamp').reindex(full_range)

        # Interpolar valores numéricos
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        df[numeric_cols] = df[numeric_cols].interpolate(method='linear')

        # Converter de volta para lista de dicts
        df = df.reset_index()
        df = df.rename(columns={'index': 'timestamp'})

        return df.to_dict('records')

    async def _fetch_clickhouse_training_data(self, window_days: int) -> list:
        """Busca dados de treinamento do ClickHouse."""
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=window_days)

        try:
            data = await self.clickhouse.query_execution_timeseries(
                start_timestamp=start_time,
                end_timestamp=end_time,
                aggregation_interval='1h'
            )

            logger.info(f"Buscados {len(data)} pontos do ClickHouse")
            return data

        except Exception as e:
            logger.error(f"Erro ao buscar dados do ClickHouse: {e}")
            return []

    async def _fetch_optimization_history(self, days: int) -> list:
        """Busca histórico de otimizações do MongoDB."""
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)

            cursor = self.mongodb.db.optimization_ledger.find({
                'timestamp': {'$gte': cutoff},
                'optimization_type': 'scheduling'
            }).sort('timestamp', -1).limit(10000)

            history = await cursor.to_list(length=10000)

            logger.info(f"Buscados {len(history)} registros de otimização")
            return history

        except Exception as e:
            logger.error(f"Erro ao buscar histórico: {e}")
            return []

    def _extract_sar_tuples(self, optimization_history: list) -> list:
        """
        Extrai tuples (state, action, reward, next_state) do histórico.

        Args:
            optimization_history: Registros de otimizações do MongoDB

        Returns:
            Lista de tuples (state, action, reward, next_state)
        """
        tuples = []

        for i in range(len(optimization_history) - 1):
            record = optimization_history[i]
            next_record = optimization_history[i + 1]

            state = record.get('state_before', {})
            action = record.get('action', '')
            reward = record.get('reward', 0)
            next_state = next_record.get('state_before', {})

            if state and action and next_state:
                # Converter action string para enum
                from .scheduling_optimizer import SchedulingAction
                try:
                    action_enum = SchedulingAction(action)
                    tuples.append((state, action_enum, reward, next_state))
                except ValueError:
                    continue

        logger.debug(f"Extraídos {len(tuples)} SAR tuples")
        return tuples

    async def _evaluate_policy_simulation(self, tuples: list) -> Dict:
        """
        Avalia política usando simulação com tuples históricos.

        Args:
            tuples: Lista de (state, action, reward, next_state)

        Returns:
            Dict com métricas de avaliação
        """
        if not tuples:
            return {'average_reward': 0, 'success_rate': 0}

        # Simular aplicação da política atual
        correct_actions = 0
        total_reward = 0

        for state, actual_action, actual_reward, next_state in tuples:
            # Prever ação usando política atual
            recommendation = await self.scheduling_optimizer.optimize_scheduling(
                current_state=state,
                load_forecast=None
            )

            predicted_action = recommendation.get('action', '')

            # Verificar se coincide
            if predicted_action == actual_action.value:
                correct_actions += 1

            total_reward += actual_reward

        success_rate = correct_actions / len(tuples) if tuples else 0
        average_reward = total_reward / len(tuples) if tuples else 0

        return {
            'average_reward': average_reward,
            'success_rate': success_rate,
            'tuples_evaluated': len(tuples),
        }

    async def _retry_training(self, model_type: str, error: Exception, max_retries: int = 3) -> Dict:
        """
        Retry logic para treinamento com backoff exponencial.

        Args:
            model_type: 'load_predictor' ou 'scheduling_optimizer'
            error: Exceção original
            max_retries: Número máximo de tentativas

        Returns:
            Resultado da última tentativa
        """
        for attempt in range(max_retries):
            logger.warning(f"Retry {attempt+1}/{max_retries} para {model_type}")

            # Backoff exponencial
            await asyncio.sleep(2 ** attempt * 60)  # 1min, 2min, 4min

            try:
                if model_type == 'load_predictor':
                    return await self.train_load_predictor()
                elif model_type == 'scheduling_optimizer':
                    return await self.train_scheduling_optimizer()
            except Exception as e:
                logger.error(f"Retry falhou: {e}")
                if attempt == max_retries - 1:
                    # Última tentativa falhou
                    return {
                        'success': False,
                        'error': str(e),
                        'retries': max_retries
                    }

        return {'success': False, 'error': 'Max retries exceeded'}
