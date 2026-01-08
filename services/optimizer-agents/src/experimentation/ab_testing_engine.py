# -*- coding: utf-8 -*-
"""
Engine Principal de A/B Testing.

Coordena toda a logica de testes A/B, incluindo:
- Criacao e gerenciamento de testes
- Atribuicao de entidades a grupos
- Coleta de metricas
- Analise estatistica
- Verificacao de parada antecipada
"""

import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from src.experimentation.randomization import (
    BaseRandomizer,
    Group,
    RandomizationStrategyType,
    get_randomizer,
)
from src.experimentation.statistical_analysis import (
    StatisticalAnalyzer,
    ContinuousMetricResult,
    BinaryMetricResult,
    BayesianResult,
)
from src.experimentation.guardrails import GuardrailMonitor
from src.experimentation.sample_size_calculator import SampleSizeCalculator

logger = structlog.get_logger()


@dataclass
class ABTestConfig:
    """Configuracao de um teste A/B."""
    experiment_id: str
    name: str
    hypothesis: str
    traffic_split: float  # Proporcao para treatment (0.0 a 1.0)
    randomization_strategy: RandomizationStrategyType
    primary_metrics: List[str]
    secondary_metrics: List[str]
    guardrails: List[Dict]
    minimum_sample_size: int
    maximum_duration_seconds: int
    early_stopping_enabled: bool
    bayesian_analysis_enabled: bool
    created_at: datetime
    created_by: str
    status: str  # "running", "completed", "aborted"
    metadata: Dict[str, Any]


@dataclass
class ABTestResults:
    """Resultados completos de um teste A/B."""
    experiment_id: str
    status: str
    control_size: int
    treatment_size: int
    primary_metrics_analysis: List[Dict]
    secondary_metrics_analysis: List[Dict]
    bayesian_analysis: Optional[List[Dict]]
    guardrails_status: Dict
    statistical_recommendation: str  # "APPLY", "REJECT", "INCONCLUSIVE"
    confidence_level: float
    early_stopped: bool
    early_stop_reason: Optional[str]
    analysis_timestamp: datetime


class ABTestingEngine:
    """
    Engine principal para gerenciamento de testes A/B.

    Fornece API completa para criar, gerenciar e analisar testes A/B
    com suporte a multiplas estrategias de randomizacao e analise estatistica.
    """

    def __init__(
        self,
        settings=None,
        mongodb_client=None,
        redis_client=None,
        metrics=None,
    ):
        """
        Inicializar ABTestingEngine.

        Args:
            settings: Configuracoes do servico
            mongodb_client: Cliente MongoDB para persistencia
            redis_client: Cliente Redis para caching
            metrics: Instancia de metricas Prometheus
        """
        self.settings = settings
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.metrics = metrics

        # Componentes
        self.statistical_analyzer = StatisticalAnalyzer(
            alpha=settings.ab_test_default_alpha if settings else 0.05
        )
        self.guardrail_monitor = GuardrailMonitor(
            mongodb_client=mongodb_client,
            redis_client=redis_client,
            statistical_analyzer=self.statistical_analyzer,
            min_sample_size=settings.ab_test_min_sample_size if settings else 100,
        )
        self.sample_calculator = SampleSizeCalculator()

        # Cache de randomizadores por experimento
        self._randomizers: Dict[str, BaseRandomizer] = {}

        logger.info("ab_testing_engine_initialized")

    async def create_ab_test(
        self,
        name: str,
        hypothesis: str,
        primary_metrics: List[str],
        traffic_split: float = 0.5,
        randomization_strategy: RandomizationStrategyType = RandomizationStrategyType.RANDOM,
        secondary_metrics: Optional[List[str]] = None,
        guardrails: Optional[List[Dict]] = None,
        minimum_sample_size: int = 100,
        maximum_duration_seconds: int = 604800,  # 7 dias
        early_stopping_enabled: bool = True,
        bayesian_analysis_enabled: bool = True,
        created_by: str = "ab_testing_engine",
        metadata: Optional[Dict] = None,
    ) -> ABTestConfig:
        """
        Criar novo teste A/B.

        Args:
            name: Nome do teste
            hypothesis: Hipotese a ser testada
            primary_metrics: Metricas primarias para decisao
            traffic_split: Proporcao de trafego para treatment
            randomization_strategy: Estrategia de randomizacao
            secondary_metrics: Metricas secundarias (observacionais)
            guardrails: Configuracao de guardrails de seguranca
            minimum_sample_size: Tamanho minimo de amostra por grupo
            maximum_duration_seconds: Duracao maxima do experimento
            early_stopping_enabled: Habilitar parada antecipada
            bayesian_analysis_enabled: Habilitar analise Bayesiana
            created_by: Identificador do criador
            metadata: Metadados adicionais

        Returns:
            Configuracao do teste criado
        """
        experiment_id = str(uuid.uuid4())
        now = datetime.utcnow()

        config = ABTestConfig(
            experiment_id=experiment_id,
            name=name,
            hypothesis=hypothesis,
            traffic_split=traffic_split,
            randomization_strategy=randomization_strategy,
            primary_metrics=primary_metrics,
            secondary_metrics=secondary_metrics or [],
            guardrails=guardrails or [],
            minimum_sample_size=minimum_sample_size,
            maximum_duration_seconds=maximum_duration_seconds,
            early_stopping_enabled=early_stopping_enabled,
            bayesian_analysis_enabled=bayesian_analysis_enabled,
            created_at=now,
            created_by=created_by,
            status="running",
            metadata=metadata or {},
        )

        # Criar randomizador para este experimento
        self._randomizers[experiment_id] = get_randomizer(
            strategy=randomization_strategy,
            redis_client=self.redis_client,
        )

        # Inicializar estruturas no Redis
        await self._initialize_experiment_structures(config)

        # Persistir no MongoDB
        if self.mongodb_client:
            await self._save_experiment_config(config)

        # Registrar metrica
        if self.metrics:
            self.metrics.increment_counter(
                "experiments_submitted_total",
                {"experiment_type": "A_B_TEST"},
            )

        logger.info(
            "ab_test_created",
            experiment_id=experiment_id,
            name=name,
            traffic_split=traffic_split,
            minimum_sample_size=minimum_sample_size,
        )

        return config

    async def assign_to_group(
        self,
        entity_id: str,
        experiment_id: str,
        strata_key: Optional[str] = None,
        block_size: int = 10,
    ) -> str:
        """
        Atribuir entidade a um grupo (control ou treatment).

        Args:
            entity_id: Identificador unico da entidade
            experiment_id: ID do experimento
            strata_key: Chave de estrato (para randomizacao estratificada)
            block_size: Tamanho do bloco (para randomizacao em blocos)

        Returns:
            Grupo atribuido ("control" ou "treatment")
        """
        # Obter configuracao do experimento
        config = await self._get_experiment_config(experiment_id)
        if not config:
            raise ValueError(f"Experimento {experiment_id} nao encontrado")

        # Obter randomizador
        randomizer = self._randomizers.get(experiment_id)
        if not randomizer:
            randomizer = get_randomizer(
                strategy=config.randomization_strategy,
                redis_client=self.redis_client,
            )
            self._randomizers[experiment_id] = randomizer

        # Atribuir grupo
        group = await randomizer.assign(
            entity_id=entity_id,
            experiment_id=experiment_id,
            traffic_split=config.traffic_split,
            strata_key=strata_key,
            block_size=block_size,
        )

        # Atualizar contadores
        await self._increment_group_counter(experiment_id, group)

        # Registrar metrica
        if self.metrics:
            self.metrics.increment_counter(
                "ab_test_assignments_total",
                {"experiment_id": experiment_id, "group": group.value},
            )

        logger.debug(
            "entity_assigned_to_group",
            entity_id=entity_id,
            experiment_id=experiment_id,
            group=group.value,
        )

        return group.value

    async def collect_metrics(
        self,
        experiment_id: str,
        group: str,
        metrics: Dict[str, float],
        entity_id: Optional[str] = None,
    ) -> None:
        """
        Coletar metricas para um grupo do experimento.

        Args:
            experiment_id: ID do experimento
            group: Grupo ("control" ou "treatment")
            metrics: Dicionario de metricas coletadas
            entity_id: ID da entidade (opcional)
        """
        if not self.redis_client:
            logger.warning("redis_client_not_configured_skipping_metrics_collection")
            return

        # Armazenar cada metrica
        for metric_name, value in metrics.items():
            key = f"ab_test:{experiment_id}:metrics:{group}:{metric_name}"

            try:
                # Usar LPUSH para manter lista de valores
                await self.redis_client.lpush(key, str(value))

                # Limitar tamanho da lista (manter ultimas 100k observacoes)
                await self.redis_client.ltrim(key, 0, 99999)

                # TTL de 14 dias
                await self.redis_client.expire(key, 1209600)
            except Exception as e:
                logger.warning(
                    "failed_to_collect_metric",
                    experiment_id=experiment_id,
                    metric_name=metric_name,
                    error=str(e),
                )

        logger.debug(
            "metrics_collected",
            experiment_id=experiment_id,
            group=group,
            metrics_count=len(metrics),
        )

    async def analyze_results(
        self,
        experiment_id: str,
    ) -> ABTestResults:
        """
        Analisar resultados completos do experimento.

        Identifica metricas binarias e aplica analise apropriada
        (analyze_binary_metric para binarias, analyze_continuous_metric para continuas).

        Args:
            experiment_id: ID do experimento

        Returns:
            Resultados com analise estatistica completa
        """
        # Obter configuracao
        config = await self._get_experiment_config(experiment_id)
        if not config:
            raise ValueError(f"Experimento {experiment_id} nao encontrado")

        # Obter metricas coletadas
        control_metrics = await self._get_collected_metrics(experiment_id, "control")
        treatment_metrics = await self._get_collected_metrics(experiment_id, "treatment")

        # Obter tamanhos dos grupos
        control_size = await self._get_group_size(experiment_id, "control")
        treatment_size = await self._get_group_size(experiment_id, "treatment")

        # Analisar metricas primarias (identificando binarias vs continuas)
        primary_analysis = []
        for metric_name in config.primary_metrics:
            control_data = control_metrics.get(metric_name, [])
            treatment_data = treatment_metrics.get(metric_name, [])

            if control_data and treatment_data:
                # Verificar se metrica e binaria
                if self._is_binary_metric(metric_name, control_data):
                    # Analise para metrica binaria
                    result = self._analyze_binary_from_data(
                        control_data=control_data,
                        treatment_data=treatment_data,
                        metric_name=metric_name,
                    )
                else:
                    # Analise para metrica continua
                    result = self.statistical_analyzer.analyze_continuous_metric(
                        control_data=control_data,
                        treatment_data=treatment_data,
                        metric_name=metric_name,
                    )
                primary_analysis.append(asdict(result))

        # Analisar metricas secundarias (identificando binarias vs continuas)
        secondary_analysis = []
        for metric_name in config.secondary_metrics:
            control_data = control_metrics.get(metric_name, [])
            treatment_data = treatment_metrics.get(metric_name, [])

            if control_data and treatment_data:
                # Verificar se metrica e binaria
                if self._is_binary_metric(metric_name, control_data):
                    # Analise para metrica binaria
                    result = self._analyze_binary_from_data(
                        control_data=control_data,
                        treatment_data=treatment_data,
                        metric_name=metric_name,
                    )
                else:
                    # Analise para metrica continua
                    result = self.statistical_analyzer.analyze_continuous_metric(
                        control_data=control_data,
                        treatment_data=treatment_data,
                        metric_name=metric_name,
                    )
                secondary_analysis.append(asdict(result))

        # Analise Bayesiana (se habilitada)
        bayesian_analysis = None
        if config.bayesian_analysis_enabled:
            bayesian_analysis = []
            for metric_name in config.primary_metrics:
                control_data = control_metrics.get(metric_name, [])
                treatment_data = treatment_metrics.get(metric_name, [])

                if control_data and treatment_data:
                    result = self.statistical_analyzer.bayesian_analysis(
                        control_data=control_data,
                        treatment_data=treatment_data,
                        metric_name=metric_name,
                    )
                    bayesian_analysis.append(asdict(result))

        # Verificar guardrails
        guardrails_result = await self.guardrail_monitor.check_guardrails(
            experiment_id=experiment_id,
            guardrails_config=config.guardrails,
            control_metrics=control_metrics,
            treatment_metrics=treatment_metrics,
        )

        # Gerar recomendacao
        recommendation, confidence = self._generate_recommendation(
            primary_analysis=primary_analysis,
            guardrails_result=guardrails_result,
            bayesian_analysis=bayesian_analysis,
        )

        # Verificar parada antecipada
        early_stopped = False
        early_stop_reason = None

        if config.early_stopping_enabled:
            early_check = await self.should_stop_early(experiment_id)
            early_stopped = early_check.get("can_stop", False)
            if early_stopped:
                early_stop_reason = early_check.get("reason")

        # Registrar metricas Prometheus
        if self.metrics:
            for analysis in primary_analysis:
                self.metrics.set_gauge(
                    "ab_test_statistical_significance",
                    analysis.get("p_value", 1.0),
                    {"experiment_id": experiment_id, "metric_name": analysis.get("metric_name", "")},
                )
                self.metrics.set_gauge(
                    "ab_test_effect_size",
                    analysis.get("effect_size", 0.0),
                    {"experiment_id": experiment_id, "metric_name": analysis.get("metric_name", "")},
                )

            self.metrics.set_gauge(
                "ab_test_sample_size",
                control_size,
                {"experiment_id": experiment_id, "group": "control"},
            )
            self.metrics.set_gauge(
                "ab_test_sample_size",
                treatment_size,
                {"experiment_id": experiment_id, "group": "treatment"},
            )

        results = ABTestResults(
            experiment_id=experiment_id,
            status=config.status,
            control_size=control_size,
            treatment_size=treatment_size,
            primary_metrics_analysis=primary_analysis,
            secondary_metrics_analysis=secondary_analysis,
            bayesian_analysis=bayesian_analysis,
            guardrails_status={
                "violated": guardrails_result.violated,
                "should_abort": guardrails_result.should_abort,
                "violations_count": len(guardrails_result.violations),
            },
            statistical_recommendation=recommendation,
            confidence_level=confidence,
            early_stopped=early_stopped,
            early_stop_reason=early_stop_reason,
            analysis_timestamp=datetime.utcnow(),
        )

        logger.info(
            "ab_test_results_analyzed",
            experiment_id=experiment_id,
            control_size=control_size,
            treatment_size=treatment_size,
            recommendation=recommendation,
            confidence=confidence,
        )

        return results

    async def should_stop_early(
        self,
        experiment_id: str,
    ) -> Dict:
        """
        Verificar se experimento pode parar antecipadamente.

        Usa Sequential Testing (SPRT) para determinar se
        significancia foi atingida antes do tempo previsto.

        Args:
            experiment_id: ID do experimento

        Returns:
            Dict com can_stop, reason e decision
        """
        config = await self._get_experiment_config(experiment_id)
        if not config:
            return {"can_stop": False, "reason": "Experimento nao encontrado"}

        if not config.early_stopping_enabled:
            return {"can_stop": False, "reason": "Parada antecipada desabilitada"}

        # Obter metricas
        control_metrics = await self._get_collected_metrics(experiment_id, "control")
        treatment_metrics = await self._get_collected_metrics(experiment_id, "treatment")

        # Verificar tamanho minimo
        control_size = await self._get_group_size(experiment_id, "control")
        treatment_size = await self._get_group_size(experiment_id, "treatment")

        min_size = config.minimum_sample_size
        if control_size < min_size or treatment_size < min_size:
            return {
                "can_stop": False,
                "reason": f"Amostra insuficiente: control={control_size}, treatment={treatment_size}, min={min_size}",
            }

        # Aplicar sequential testing na metrica primaria principal
        if config.primary_metrics:
            primary_metric = config.primary_metrics[0]
            control_data = control_metrics.get(primary_metric, [])
            treatment_data = treatment_metrics.get(primary_metric, [])

            if control_data and treatment_data:
                result = await self.guardrail_monitor.apply_sequential_testing(
                    experiment_id=experiment_id,
                    control_data=control_data,
                    treatment_data=treatment_data,
                )

                if result.can_stop_early:
                    return {
                        "can_stop": True,
                        "reason": f"Sequential test: {result.decision}",
                        "decision": result.decision,
                        "likelihood_ratio": result.likelihood_ratio,
                    }

        return {"can_stop": False, "reason": "Significancia ainda nao atingida"}

    async def _validate_sample_size(
        self,
        experiment_id: str,
    ) -> Dict:
        """Validar se tamanho de amostra e suficiente."""
        config = await self._get_experiment_config(experiment_id)
        if not config:
            return {"valid": False, "reason": "Experimento nao encontrado"}

        control_size = await self._get_group_size(experiment_id, "control")
        treatment_size = await self._get_group_size(experiment_id, "treatment")

        min_size = config.minimum_sample_size

        return {
            "valid": control_size >= min_size and treatment_size >= min_size,
            "control_size": control_size,
            "treatment_size": treatment_size,
            "minimum_required": min_size,
            "percentage_complete": min(
                (control_size + treatment_size) / (min_size * 2) * 100, 100
            ),
        }

    # Metodos auxiliares

    async def _initialize_experiment_structures(self, config: ABTestConfig) -> None:
        """Inicializar estruturas do experimento no Redis."""
        if not self.redis_client:
            return

        try:
            # Inicializar contadores de grupos
            control_key = f"ab_test:{config.experiment_id}:group_size:control"
            treatment_key = f"ab_test:{config.experiment_id}:group_size:treatment"

            await self.redis_client.set(control_key, "0")
            await self.redis_client.set(treatment_key, "0")

            # TTL de 14 dias
            await self.redis_client.expire(control_key, 1209600)
            await self.redis_client.expire(treatment_key, 1209600)

        except Exception as e:
            logger.warning("failed_to_initialize_experiment_structures", error=str(e))

    async def _save_experiment_config(self, config: ABTestConfig) -> None:
        """Salvar configuracao do experimento no MongoDB."""
        if not self.mongodb_client:
            return

        try:
            doc = {
                "experiment_id": config.experiment_id,
                "name": config.name,
                "hypothesis": config.hypothesis,
                "traffic_split": config.traffic_split,
                "randomization_strategy": config.randomization_strategy.value,
                "primary_metrics": config.primary_metrics,
                "secondary_metrics": config.secondary_metrics,
                "guardrails": config.guardrails,
                "minimum_sample_size": config.minimum_sample_size,
                "maximum_duration_seconds": config.maximum_duration_seconds,
                "early_stopping_enabled": config.early_stopping_enabled,
                "bayesian_analysis_enabled": config.bayesian_analysis_enabled,
                "created_at": config.created_at,
                "created_by": config.created_by,
                "status": config.status,
                "metadata": config.metadata,
                "experiment_type": "A_B_TEST",
            }

            await self.mongodb_client.save_experiment(doc)
        except Exception as e:
            logger.warning("failed_to_save_experiment_config", error=str(e))

    async def _get_experiment_config(self, experiment_id: str) -> Optional[ABTestConfig]:
        """Recuperar configuracao do experimento."""
        if not self.mongodb_client:
            return None

        try:
            doc = await self.mongodb_client.get_experiment(experiment_id)
            if not doc:
                return None

            return ABTestConfig(
                experiment_id=doc["experiment_id"],
                name=doc.get("name", ""),
                hypothesis=doc.get("hypothesis", ""),
                traffic_split=doc.get("traffic_split", 0.5),
                randomization_strategy=RandomizationStrategyType(
                    doc.get("randomization_strategy", "RANDOM")
                ),
                primary_metrics=doc.get("primary_metrics", []),
                secondary_metrics=doc.get("secondary_metrics", []),
                guardrails=doc.get("guardrails", []),
                minimum_sample_size=doc.get("minimum_sample_size", 100),
                maximum_duration_seconds=doc.get("maximum_duration_seconds", 604800),
                early_stopping_enabled=doc.get("early_stopping_enabled", True),
                bayesian_analysis_enabled=doc.get("bayesian_analysis_enabled", True),
                created_at=doc.get("created_at", datetime.utcnow()),
                created_by=doc.get("created_by", ""),
                status=doc.get("status", "running"),
                metadata=doc.get("metadata", {}),
            )
        except Exception as e:
            logger.warning("failed_to_get_experiment_config", error=str(e))
            return None

    async def _increment_group_counter(self, experiment_id: str, group: Group) -> None:
        """Incrementar contador de grupo."""
        if not self.redis_client:
            return

        try:
            key = f"ab_test:{experiment_id}:group_size:{group.value}"
            await self.redis_client.incr(key)
        except Exception as e:
            logger.warning("failed_to_increment_group_counter", error=str(e))

    async def _get_group_size(self, experiment_id: str, group: str) -> int:
        """Obter tamanho do grupo."""
        if not self.redis_client:
            return 0

        try:
            key = f"ab_test:{experiment_id}:group_size:{group}"
            value = await self.redis_client.get(key)
            return int(value) if value else 0
        except Exception:
            return 0

    async def _get_collected_metrics(
        self,
        experiment_id: str,
        group: str,
    ) -> Dict[str, List[float]]:
        """Obter metricas coletadas para um grupo."""
        if not self.redis_client:
            return {}

        metrics = {}

        try:
            # Buscar todas as chaves de metricas para este grupo
            pattern = f"ab_test:{experiment_id}:metrics:{group}:*"
            keys = await self.redis_client.keys(pattern)

            for key in keys:
                # Extrair nome da metrica da chave
                parts = key.split(":")
                if len(parts) >= 5:
                    metric_name = parts[4]

                    # Obter valores
                    values = await self.redis_client.lrange(key, 0, -1)
                    metrics[metric_name] = [float(v) for v in values]

        except Exception as e:
            logger.warning("failed_to_get_collected_metrics", error=str(e))

        return metrics

    def _generate_recommendation(
        self,
        primary_analysis: List[Dict],
        guardrails_result,
        bayesian_analysis: Optional[List[Dict]] = None,
    ) -> tuple:
        """Gerar recomendacao baseada nas analises."""
        # Se guardrails violados, rejeitar
        if guardrails_result.should_abort:
            return "REJECT", 0.0

        if not primary_analysis:
            return "INCONCLUSIVE", 0.0

        # Verificar significancia das metricas primarias
        significant_improvements = 0
        significant_degradations = 0
        total_confidence = 0.0

        for analysis in primary_analysis:
            if analysis.get("statistically_significant", False):
                # Para metricas binarias, usar relative_risk ou odds_ratio
                # Para metricas continuas, usar effect_size
                if "effect_size" in analysis:
                    effect_size = analysis.get("effect_size", 0)
                elif "relative_risk" in analysis:
                    # Para metricas binarias: RR > 1 indica melhoria (mais conversoes)
                    # ou RR < 1 indica melhoria (menos erros) dependendo da metrica
                    effect_size = analysis.get("relative_risk", 1.0) - 1.0
                else:
                    effect_size = 0

                if effect_size > 0:
                    significant_improvements += 1
                else:
                    significant_degradations += 1

            total_confidence += (1 - analysis.get("p_value", 1.0))

        avg_confidence = total_confidence / len(primary_analysis) if primary_analysis else 0.0

        # Considerar analise Bayesiana se disponivel
        bayesian_support = False
        if bayesian_analysis:
            for ba in bayesian_analysis:
                if ba.get("probability_of_superiority", 0) > 0.95:
                    bayesian_support = True
                    break

        # Decisao
        if significant_degradations > 0:
            return "REJECT", avg_confidence
        elif significant_improvements > 0 and bayesian_support:
            return "APPLY", avg_confidence
        elif significant_improvements > 0:
            return "APPLY", avg_confidence * 0.9  # Menor confianca sem Bayesiano
        else:
            return "INCONCLUSIVE", avg_confidence

    def _is_binary_metric(self, metric_name: str, data: List[float]) -> bool:
        """
        Determinar se metrica e binaria baseado no nome ou nos dados.

        Uma metrica e considerada binaria se:
        - Nome contem sufixos como _rate, _ratio, _conversion, _pct
        - Nome contem prefixos como error_, success_, failure_
        - Todos os valores nos dados sao 0 ou 1

        Args:
            metric_name: Nome da metrica
            data: Lista de valores coletados

        Returns:
            True se metrica for binaria, False caso contrario
        """
        # Sufixos que indicam metricas binarias
        binary_suffixes = ['_rate', '_ratio', '_percentage', '_pct', '_conversion']
        binary_prefixes = ['error_', 'success_', 'failure_', 'conversion_', 'click_']

        metric_lower = metric_name.lower()

        # Verificar por nome
        for suffix in binary_suffixes:
            if metric_lower.endswith(suffix):
                return True

        for prefix in binary_prefixes:
            if metric_lower.startswith(prefix):
                return True

        # Verificar por dados: se todos os valores sao 0 ou 1, e binaria
        if data:
            all_binary = all(v == 0.0 or v == 1.0 for v in data)
            if all_binary and len(data) >= 10:  # Minimo de 10 observacoes
                return True

        return False

    def _analyze_binary_from_data(
        self,
        control_data: List[float],
        treatment_data: List[float],
        metric_name: str,
    ) -> BinaryMetricResult:
        """
        Analisar metrica binaria a partir de dados coletados.

        Converte lista de valores (0/1 ou taxas) para contagens de
        sucesso/total e chama StatisticalAnalyzer.analyze_binary_metric().

        Args:
            control_data: Dados do grupo controle
            treatment_data: Dados do grupo tratamento
            metric_name: Nome da metrica

        Returns:
            BinaryMetricResult com analise estatistica
        """
        # Converter dados para contagens de sucesso/total
        # Se valores sao 0/1, contar sucessos diretamente
        # Se valores sao taxas (0-1), calcular media e converter para contagem estimada
        control_total = len(control_data)
        treatment_total = len(treatment_data)

        # Verificar se dados sao binarios (0/1) ou taxas
        control_is_binary = all(v == 0.0 or v == 1.0 for v in control_data) if control_data else False
        treatment_is_binary = all(v == 0.0 or v == 1.0 for v in treatment_data) if treatment_data else False

        if control_is_binary and treatment_is_binary:
            # Dados binarios puros: contar sucessos
            control_successes = int(sum(control_data))
            treatment_successes = int(sum(treatment_data))
        else:
            # Dados sao taxas: usar media * total como estimativa de sucessos
            control_mean = sum(control_data) / len(control_data) if control_data else 0.0
            treatment_mean = sum(treatment_data) / len(treatment_data) if treatment_data else 0.0

            control_successes = int(control_mean * control_total)
            treatment_successes = int(treatment_mean * treatment_total)

        # Chamar analyze_binary_metric do StatisticalAnalyzer
        result = self.statistical_analyzer.analyze_binary_metric(
            control_successes=control_successes,
            control_total=control_total,
            treatment_successes=treatment_successes,
            treatment_total=treatment_total,
            metric_name=metric_name,
        )

        logger.debug(
            "binary_metric_analyzed",
            metric_name=metric_name,
            control_rate=result.control_rate,
            treatment_rate=result.treatment_rate,
            relative_risk=result.relative_risk,
            p_value=result.p_value,
            significant=result.statistically_significant,
        )

        return result
