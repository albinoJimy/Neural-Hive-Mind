"""
Approval Service - Logica de negocio para aprovacao de planos

Camada de servico que coordena operacoes entre API, MongoDB e Kafka.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

import structlog
from pymongo.errors import DuplicateKeyError

from src.clients.cognitive_ledger_client import CognitiveLedgerClient
from src.clients.feature_store_client import FeatureStoreClient
from src.clients.mongodb_client import MongoDBClient
from src.config.settings import Settings
from neural_hive_approval_common import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStats,
    ApprovalStatus,
)
from src.models import ApprovalResponse, RevertResponse
from src.observability.metrics import NeuralHiveMetrics
from src.producers.approval_response_producer import ApprovalResponseProducer

# Import opcional - pode nao estar disponivel em todos os ambientes
try:
    from neural_hive_specialists.feedback import FeedbackCollector
except ImportError:
    FeedbackCollector = None

# Active Learning components (opcional)
try:
    from neural_hive_specialists.feedback.active_learning.balance_analyzer import (
        DatasetBalanceAnalyzer,
    )
    from neural_hive_specialists.feedback.active_learning.feedback_queue import (
        PriorityFeedbackQueue,
    )
    from neural_hive_specialists.feedback.active_learning.learning_strategy import (
        ActiveLearningStrategy,
    )

    HAS_ACTIVE_LEARNING = True
except ImportError:
    DatasetBalanceAnalyzer = None
    ActiveLearningStrategy = None
    PriorityFeedbackQueue = None
    HAS_ACTIVE_LEARNING = False

# NLP Feature Extractor (opcional, para extracao de domain)
try:
    from neural_hive_specialists.feature_extraction.nlp_feature_extractor import (
        NLPFeatureExtractor,
        get_nlp_extractor,
    )

    HAS_NLP_EXTRACTOR = True
except ImportError:
    NLPFeatureExtractor = None
    get_nlp_extractor = None
    HAS_NLP_EXTRACTOR = False

logger = structlog.get_logger()


class ApprovalService:
    """Servico de logica de negocio para aprovacoes"""

    def __init__(
        self,
        settings: Settings,
        mongodb_client: MongoDBClient,
        response_producer: ApprovalResponseProducer,
        metrics: NeuralHiveMetrics,
        feedback_collector: Optional[Any] = None,
        ledger_client: Optional[CognitiveLedgerClient] = None,
        ml_predictor: Optional[Any] = None,
        balance_analyzer: Optional[Any] = None,
        learning_strategy: Optional[Any] = None,
        priority_queue: Optional[Any] = None,
        feature_store_client: Optional[FeatureStoreClient] = None,
    ):
        self.settings = settings
        self.mongodb_client = mongodb_client
        self.response_producer = response_producer
        self.metrics = metrics
        self.feedback_collector = feedback_collector
        self.ledger_client = ledger_client
        self.ml_predictor = ml_predictor
        self.feature_store_client = feature_store_client

        # Active Learning components (opcional)
        self.balance_analyzer = balance_analyzer
        self.learning_strategy = learning_strategy
        self.priority_queue = priority_queue

        self.active_learning_enabled = all(
            [
                (
                    settings.enable_active_learning
                    if hasattr(settings, "enable_active_learning")
                    else False
                ),
                HAS_ACTIVE_LEARNING,
                balance_analyzer is not None,
                learning_strategy is not None,
                priority_queue is not None,
            ]
        )

        # NLP Extractor para extracao de domain (cache singleton)
        self._nlp_extractor: Optional[NLPFeatureExtractor] = None
        if HAS_NLP_EXTRACTOR:
            try:
                self._nlp_extractor = get_nlp_extractor()
            except Exception as e:
                logger.warning("nlp_extractor_init_failed", error=str(e))

    async def process_approval_request(self, approval_request: ApprovalRequest) -> ApprovalRequest:
        """
        Processa novo request de aprovacao recebido do Kafka

        Args:
            approval_request: ApprovalRequest ja deserializado pelo consumer

        Returns:
            ApprovalRequest criado e persistido

        Raises:
            DuplicateKeyError: Se plan_id ja existe
            ValueError: Se dados invalidos
        """
        try:
            # Valida campos obrigatorios
            if not approval_request.plan_id or not approval_request.intent_id:
                raise ValueError("plan_id e intent_id sao obrigatorios")

            # Persiste no MongoDB
            await self.mongodb_client.save_approval_request(approval_request)

            # Feature Store: computar features assincronamente
            await self._maybe_compute_features(approval_request)

            # Emite metricas
            self.metrics.increment_approval_requests_received(
                risk_band=approval_request.risk_band, is_destructive=approval_request.is_destructive
            )
            self.metrics.update_pending_gauge()

            # Active Learning: enfileirar caso se aplica
            await self._maybe_enqueue_for_active_learning(approval_request)

            logger.info(
                "Approval request processado",
                plan_id=approval_request.plan_id,
                intent_id=approval_request.intent_id,
                risk_band=approval_request.risk_band,
                is_destructive=approval_request.is_destructive,
            )

            return approval_request

        except DuplicateKeyError:
            logger.warning(
                "Plan ja existe no sistema de aprovacao", plan_id=approval_request.plan_id
            )
            raise
        except Exception as e:
            logger.error(
                "Erro ao processar approval request", error=str(e), plan_id=approval_request.plan_id
            )
            raise

    async def _maybe_compute_features(self, approval_request: ApprovalRequest) -> None:
        """
        Computa features do plano no Feature Store de forma assíncrona.

        Args:
            approval_request: ApprovalRequest com cognitive_plan
        """
        if not self.feature_store_client:
            return

        try:
            # Extrai cognitive_plan do approval request
            cognitive_plan = approval_request.cognitive_plan
            if not cognitive_plan:
                logger.debug(
                    "feature_store_skip_no_cognitive_plan", plan_id=approval_request.plan_id
                )
                return

            # Computa features de forma assíncrona (não bloqueia o fluxo)
            asyncio.create_task(
                self.feature_store_client.compute_and_save_features(
                    plan_id=approval_request.plan_id,
                    cognitive_plan=cognitive_plan,
                    force_recompute=False,
                )
            )

            logger.debug("feature_store_computation_scheduled", plan_id=approval_request.plan_id)

        except Exception as e:
            # Erros no Feature Store não devem bloquear o approval
            logger.warning(
                "feature_store_computation_failed", plan_id=approval_request.plan_id, error=str(e)
            )

    async def _maybe_enqueue_for_active_learning(self, approval_request: ApprovalRequest) -> None:
        """
        Avalia se o approval request deve ser enfileirado para active learning.

        Usa ActiveLearningStrategy para calcular valor informacional e
        PriorityFeedbackQueue para enfileirar casos de alto valor.

        Args:
            approval_request: ApprovalRequest a avaliar
        """
        # Skip se active learning não habilitado
        if not self.active_learning_enabled:
            return

        try:
            # Obter decisão ML se disponível (para contexto)
            ml_decision = None
            if self.ml_predictor and self.ml_predictor.is_enabled():
                ml_result = await self.ml_predictor.get_auto_decision(
                    intent_text=approval_request.original_intent_text or "",
                    risk_band=approval_request.risk_band,
                )
                if ml_result:
                    ml_decision = ml_result.get("auto_decision")
                    ml_confidence = ml_result.get("confidence", 0.5)
                else:
                    ml_confidence = 0.5
            else:
                ml_confidence = 0.5

            # Extrair domain do texto da intencao
            domain = self._extract_domain_from_text(approval_request.original_intent_text)

            # Calcular valor informacional
            information_value = await self.learning_strategy.calculate_information_value(
                plan_id=approval_request.plan_id,
                intent_text=approval_request.original_intent_text,
                predicted_decision=ml_decision,
                confidence=ml_confidence,
                domain=domain,
            )

            # Enfileirar se valor informacional acima do threshold
            min_value = self.settings.active_learning_min_information_value
            if information_value >= min_value:
                intent_preview = (
                    approval_request.original_intent_text[:100]
                    if approval_request.original_intent_text
                    else "N/A"
                )

                priority_reason = self._get_priority_reason(information_value, ml_confidence)

                await self.priority_queue.enqueue_plan_for_review(
                    plan_id=approval_request.plan_id,
                    intent_text=approval_request.original_intent_text,
                    intent_preview=intent_preview,
                    information_value=information_value,
                    priority_reason=priority_reason,
                    domain=domain,
                    confidence=ml_confidence,
                    predicted_decision=ml_decision,
                )

                logger.info(
                    "active_learning_case_enqueued",
                    plan_id=approval_request.plan_id,
                    information_value=information_value,
                    priority_reason=priority_reason,
                )
            else:
                logger.debug(
                    "active_learning_case_below_threshold",
                    plan_id=approval_request.plan_id,
                    information_value=information_value,
                    threshold=min_value,
                )

        except Exception as e:
            # Erros de active learning não devem bloquear o fluxo principal
            logger.error(
                "active_learning_enqueue_failed", plan_id=approval_request.plan_id, error=str(e)
            )

    def _extract_domain_from_text(self, intent_text: Optional[str]) -> Optional[str]:
        """
        Extrai dominio primario do texto da intencao usando NLPFeatureExtractor.

        Args:
            intent_text: Texto da intencao do usuario

        Returns:
            Dominio primario (ex: 'security', 'performance') ou None
        """
        if not intent_text or not self._nlp_extractor:
            return None

        try:
            features = self._nlp_extractor.extract_features(intent_text)
            return features.get("primary_domain")
        except Exception as e:
            logger.warning(
                "domain_extraction_failed",
                intent_text_preview=intent_text[:50] if intent_text else None,
                error=str(e),
            )
            return None

    def _get_priority_reason(self, information_value: float, confidence: float) -> str:
        """Gera razão da prioridade baseado em valor informacional e confiança."""
        reasons = []

        if information_value >= 0.8:
            reasons.append("valor informacional muito alto")
        elif information_value >= 0.6:
            reasons.append("valor informacional alto")

        if confidence < 0.4:
            reasons.append("baixa confiança")
        elif confidence < 0.6:
            reasons.append("confiança moderada")

        return " + ".join(reasons) if reasons else "active learning"

    async def get_ml_prediction(self, plan_id: str) -> Optional[dict[str, Any]]:
        """
        Obtém predição ML para um plano de aprovação.

        Args:
            plan_id: ID do plano

        Returns:
            Dicionário com prediction ou None se ML não disponível
        """
        if not self.ml_predictor or not self.ml_predictor.is_enabled():
            return None

        try:
            # Buscar approval request para obter texto e risco
            approval = await self.mongodb_client.get_approval_by_plan_id(plan_id)
            if not approval:
                logger.warning("ml_prediction_approval_not_found", plan_id=plan_id)
                return None

            intent_text = approval.original_intent_text
            if not intent_text:
                logger.debug("ml_prediction_no_intent_text", plan_id=plan_id)
                return None

            # Buscar opiniões para obter confiança média dos especialistas
            specialist_confidence = 0.5
            if self.ledger_client:
                try:
                    opinions = await self.ledger_client.get_opinions_by_plan_id(plan_id)
                    if opinions:
                        confidences = [
                            op.get("confidence_score", 0.5)
                            for op in opinions
                            if op.get("confidence_score") is not None
                        ]
                        if confidences:
                            specialist_confidence = sum(confidences) / len(confidences)
                except Exception as e:
                    logger.debug("ml_prediction_cannot_fetch_opinions", error=str(e))

            # Obter predição
            prediction = await self.ml_predictor.predict_from_text(
                intent_text, specialist_confidence
            )

            if prediction:
                logger.info(
                    "ml_prediction_generated",
                    plan_id=plan_id,
                    decision=prediction["decision"],
                    confidence=prediction["confidence"],
                    model_version=prediction.get("model_version"),
                )

            return prediction

        except Exception as e:
            logger.error("ml_prediction_failed", plan_id=plan_id, error=str(e))
            return None

    async def get_auto_decision(self, plan_id: str) -> Optional[dict[str, Any]]:
        """
        Tenta obter uma decisão automática baseada em predição ML.

        A decisão automática só é aplicada se:
        - ML predictor está habilitado
        - Risco do plano está dentro do limite configurado
        - Confiança da predição está acima do threshold

        Args:
            plan_id: ID do plano

        Returns:
            Dicionário com auto_decision ou None se não houver decisão automática
        """
        if not self.ml_predictor or not self.ml_predictor.is_enabled():
            return None

        try:
            # Buscar approval request
            approval = await self.mongodb_client.get_approval_by_plan_id(plan_id)
            if not approval:
                return None

            intent_text = approval.original_intent_text
            if not intent_text:
                return None

            # Obter decisão automática do ML predictor
            auto_decision = await self.ml_predictor.get_auto_decision(
                intent_text=intent_text,
                risk_band=approval.risk_band,
                specialist_confidence=0.5,  # Pode ser obtido das opiniões
            )

            if auto_decision:
                logger.info(
                    "auto_decision_generated",
                    plan_id=plan_id,
                    auto_decision=auto_decision["auto_decision"],
                    confidence=auto_decision["confidence"],
                    reason=auto_decision["reason"],
                )

            return auto_decision

        except Exception as e:
            logger.error("auto_decision_failed", plan_id=plan_id, error=str(e))
            return None

    async def _submit_feedback_for_plan(
        self,
        plan_id: str,
        human_decision: str,
        human_rating: float,
        user_id: str,
        comments: Optional[str] = None,
        from_active_learning: bool = False,
    ) -> None:
        """
        Submete feedback ML para todas as opinioes de specialists do plano.

        Esta operacao nao bloqueia o fluxo de aprovacao/rejeicao.
        Erros sao logados mas nao propagados.

        Args:
            plan_id: ID do plano
            human_decision: Decisao humana ('approve' ou 'reject')
            human_rating: Rating numerico (0.0-1.0)
            user_id: ID do usuario que decidiu
            comments: Comentarios opcionais
            from_active_learning: Se True, marca como balanced_dataset=True
        """
        # Skip se feedback collection desabilitado
        if not self.settings.enable_feedback_collection:
            logger.debug("Feedback collection desabilitado", plan_id=plan_id)
            return

        # Skip se dependencias nao disponiveis
        if not self.feedback_collector or not self.ledger_client:
            logger.warning(
                "FeedbackCollector ou LedgerClient nao disponivel",
                plan_id=plan_id,
                has_collector=self.feedback_collector is not None,
                has_ledger=self.ledger_client is not None,
            )
            return

        try:
            # 1. Buscar texto original da intenção do plan_approvals
            intent_raw_text = None
            try:
                approval = await self.mongodb_client.get_approval_by_plan_id(plan_id)
                if approval:
                    intent_raw_text = approval.original_intent_text
            except Exception as e:
                logger.debug(
                    "Nao foi possivel buscar original_intent_text do plan_approvals",
                    plan_id=plan_id,
                    error=str(e),
                )

            # 2. Buscar opinioes do ledger cognitivo
            opinions = await self.ledger_client.get_opinions_by_plan_id(plan_id)

            if not opinions:
                logger.warning("Nenhuma opiniao encontrada no ledger para plan_id", plan_id=plan_id)
                return

            # 3. Submeter feedback para cada specialist que avaliou o plano
            feedback_ids = []
            for opinion in opinions:
                try:
                    feedback_data = {
                        "opinion_id": opinion["opinion_id"],
                        "plan_id": plan_id,
                        "specialist_type": opinion["specialist_type"],
                        "human_rating": human_rating,
                        "human_recommendation": human_decision,
                        "feedback_notes": comments or "",
                        "submitted_by": user_id,
                        "intent_raw_text": intent_raw_text,
                        "balanced_dataset": from_active_learning,
                        "collection_method": (
                            "active_learning" if from_active_learning else "automatic"
                        ),
                        "metadata": {
                            "source": "approval_service",
                            "specialist_recommendation": opinion.get("recommendation"),
                            "specialist_confidence": opinion.get("confidence_score"),
                        },
                    }

                    feedback_id = self.feedback_collector.submit_feedback(feedback_data)
                    feedback_ids.append(feedback_id)

                    logger.info(
                        "Feedback ML submetido",
                        feedback_id=feedback_id,
                        opinion_id=opinion["opinion_id"],
                        specialist_type=opinion["specialist_type"],
                        plan_id=plan_id,
                        has_intent_text=intent_raw_text is not None,
                    )

                except Exception as e:
                    logger.error(
                        "Erro ao submeter feedback para opiniao",
                        opinion_id=opinion.get("opinion_id"),
                        specialist_type=opinion.get("specialist_type"),
                        error=str(e),
                    )
                    # Verificar modo de falha para submissoes individuais
                    if self.settings.feedback_on_approval_failure_mode == "raise_error":
                        raise
                    # Continuar para proxima opiniao apenas se modo for log_and_continue
                    continue

            logger.info(
                "Feedback ML processado para plano",
                plan_id=plan_id,
                total_opinions=len(opinions),
                successful_feedbacks=len(feedback_ids),
                has_intent_text=intent_raw_text is not None,
            )

        except Exception as e:
            logger.error("Erro ao processar feedback ML", plan_id=plan_id, error=str(e))

            # Decidir comportamento baseado em configuracao
            if self.settings.feedback_on_approval_failure_mode == "raise_error":
                raise
            # Caso contrario, apenas logar e continuar

    def _submit_feedback_background(
        self,
        plan_id: str,
        human_decision: str,
        human_rating: float,
        user_id: str,
        comments: Optional[str] = None,
    ) -> Optional[asyncio.Task]:
        """
        Submete feedback ML em background sem bloquear o fluxo principal.

        Cria uma task asyncio que executa _submit_feedback_for_plan de forma
        assincrona. Erros sao logados mas nao propagados para o caller.

        Args:
            plan_id: ID do plano
            human_decision: Decisao humana ('approve' ou 'reject')
            human_rating: Rating numerico (0.0-1.0)
            user_id: ID do usuario que decidiu
            comments: Comentarios opcionais

        Returns:
            Task asyncio ou None se feedback desabilitado
        """
        # Skip se feedback collection desabilitado
        if not self.settings.enable_feedback_collection:
            logger.debug("Feedback collection desabilitado, skip background task", plan_id=plan_id)
            return None

        async def _safe_submit():
            """Wrapper que captura excecoes para nao crashar a task."""
            try:
                await self._submit_feedback_for_plan(
                    plan_id=plan_id,
                    human_decision=human_decision,
                    human_rating=human_rating,
                    user_id=user_id,
                    comments=comments,
                )
            except Exception as e:
                # Erro ja foi logado em _submit_feedback_for_plan
                # Aqui apenas garantimos que a task nao propaga excecao
                logger.warning("Background feedback task falhou", plan_id=plan_id, error=str(e))

        task = asyncio.create_task(_safe_submit())
        logger.debug(
            "Feedback task criada em background", plan_id=plan_id, task_name=task.get_name()
        )
        return task

    async def approve_plan(
        self, plan_id: str, user_id: str, comments: Optional[str] = None
    ) -> ApprovalDecision:
        """
        Aprova um plano cognitivo

        Args:
            plan_id: ID do plano
            user_id: ID do usuario que esta aprovando
            comments: Comentarios opcionais

        Returns:
            ApprovalDecision com a decisao

        Raises:
            ValueError: Se plano nao encontrado ou nao esta pendente
        """
        start_time = datetime.now(timezone.utc)

        # Busca plano
        approval = await self.mongodb_client.get_approval_by_plan_id(plan_id)
        if not approval:
            raise ValueError(f"Plano nao encontrado: {plan_id}")

        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(f"Plano nao esta pendente. Status atual: {approval.status}")

        # Cria decisao
        decision = ApprovalDecision(
            plan_id=plan_id,
            decision="approved",
            approved_by=user_id,
            approved_at=datetime.now(timezone.utc),
            comments=comments,
        )

        # Atualiza MongoDB
        updated = await self.mongodb_client.update_approval_decision(plan_id, decision)
        if not updated:
            raise ValueError("Falha ao atualizar decisao no MongoDB")

        # Publica no Kafka
        # FIX: Extrair plano completo da estrutura aninhada se necessário
        # O approval_request_consumer pode criar estrutura onde cognitive_plan
        # está aninhado dentro de outro cognitive_plan
        plan_data = approval.cognitive_plan
        if "cognitive_plan" in plan_data and isinstance(plan_data.get("cognitive_plan"), dict):
            # Estrutura aninhada detectada - usar plano interno
            plan_data = plan_data["cognitive_plan"]
            logger.info(
                "cognitive_plan_aninhado_detectado",
                plan_id=plan_id,
                achatando="usando plano interno",
            )

        response = ApprovalResponse(
            plan_id=plan_id,
            intent_id=approval.intent_id,
            decision="approved",
            approved_by=user_id,
            approved_at=decision.approved_at,
            cognitive_plan=plan_data,
        )
        await self.response_producer.send_approval_response(response)

        # Emite metricas
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        # requested_at vindo do MongoDB e tz-naive; normaliza para UTC antes de subtrair
        requested_at = approval.requested_at
        if requested_at.tzinfo is None:
            requested_at = requested_at.replace(tzinfo=timezone.utc)
        time_to_decision = (decision.approved_at - requested_at).total_seconds()

        self.metrics.increment_approvals_total("approved", approval.risk_band)
        self.metrics.observe_processing_duration(duration, "approved")
        self.metrics.observe_time_to_decision(time_to_decision, "approved", approval.risk_band)
        self.metrics.update_pending_gauge()

        logger.info(
            "Plano aprovado",
            plan_id=plan_id,
            approved_by=user_id,
            time_to_decision_seconds=time_to_decision,
        )

        # Submete feedback ML em background (nao bloqueia aprovacao)
        self._submit_feedback_background(
            plan_id=plan_id,
            human_decision="approve",
            human_rating=1.0,  # Aprovado = rating maximo
            user_id=user_id,
            comments=comments,
        )

        return decision

    async def reject_plan(
        self, plan_id: str, user_id: str, reason: str, comments: Optional[str] = None
    ) -> ApprovalDecision:
        """
        Rejeita um plano cognitivo

        Args:
            plan_id: ID do plano
            user_id: ID do usuario que esta rejeitando
            reason: Motivo da rejeicao (obrigatorio)
            comments: Comentarios opcionais

        Returns:
            ApprovalDecision com a decisao

        Raises:
            ValueError: Se plano nao encontrado, nao pendente, ou reason vazio
        """
        if not reason or not reason.strip():
            raise ValueError("Motivo da rejeicao e obrigatorio")

        start_time = datetime.now(timezone.utc)

        # Busca plano
        approval = await self.mongodb_client.get_approval_by_plan_id(plan_id)
        if not approval:
            raise ValueError(f"Plano nao encontrado: {plan_id}")

        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(f"Plano nao esta pendente. Status atual: {approval.status}")

        # Cria decisao
        decision = ApprovalDecision(
            plan_id=plan_id,
            decision="rejected",
            approved_by=user_id,
            approved_at=datetime.now(timezone.utc),
            rejection_reason=reason,
            comments=comments,
        )

        # Atualiza MongoDB
        updated = await self.mongodb_client.update_approval_decision(plan_id, decision)
        if not updated:
            raise ValueError("Falha ao atualizar decisao no MongoDB")

        # Publica no Kafka (sem cognitive_plan para rejeicoes)
        response = ApprovalResponse(
            plan_id=plan_id,
            intent_id=approval.intent_id,
            decision="rejected",
            approved_by=user_id,
            approved_at=decision.approved_at,
            rejection_reason=reason,
            cognitive_plan=None,
        )
        await self.response_producer.send_approval_response(response)

        # Emite metricas
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        # requested_at vindo do MongoDB e tz-naive; normaliza para UTC antes de subtrair
        requested_at = approval.requested_at
        if requested_at.tzinfo is None:
            requested_at = requested_at.replace(tzinfo=timezone.utc)
        time_to_decision = (decision.approved_at - requested_at).total_seconds()

        self.metrics.increment_approvals_total("rejected", approval.risk_band)
        self.metrics.observe_processing_duration(duration, "rejected")
        self.metrics.observe_time_to_decision(time_to_decision, "rejected", approval.risk_band)
        self.metrics.update_pending_gauge()

        logger.info(
            "Plano rejeitado",
            plan_id=plan_id,
            rejected_by=user_id,
            reason=reason,
            time_to_decision_seconds=time_to_decision,
        )

        # Submete feedback ML em background (nao bloqueia rejeicao)
        self._submit_feedback_background(
            plan_id=plan_id,
            human_decision="reject",
            human_rating=0.0,  # Rejeitado = rating minimo
            user_id=user_id,
            comments=f"{reason}. {comments or ''}".strip(),
        )

        return decision

    async def republish_approved_plan(
        self, plan_id: str, user_id: str, force: bool = False, comments: Optional[str] = None
    ) -> ApprovalResponse:
        """
        Republica um plano cognitivo ja aprovado no Kafka

        Util para reprocessamento de planos que falharam na republicacao
        original ou para correcao de inconsistencias.

        Args:
            plan_id: ID do plano
            user_id: ID do usuario que esta republicando
            force: Se True, bypassa validacoes adicionais
            comments: Comentarios sobre a republicacao

        Returns:
            ApprovalResponse publicado no Kafka

        Raises:
            ValueError: Se plano nao encontrado ou nao esta aprovado
        """
        start_time = datetime.now(timezone.utc)

        # Busca plano
        approval = await self.mongodb_client.get_approval_by_plan_id(plan_id)
        if not approval:
            self.metrics.increment_republish_failures("not_found")
            raise ValueError(f"Plano nao encontrado: {plan_id}")

        # Valida que plano esta aprovado
        if approval.status != ApprovalStatus.APPROVED:
            if not force:
                self.metrics.increment_republish_failures("not_approved")
                raise ValueError(
                    f"Plano nao esta aprovado. Status atual: {approval.status}. "
                    f"Use force=true para republicar mesmo assim."
                )
            logger.warning(
                "Republicacao forcada de plano nao aprovado",
                plan_id=plan_id,
                status=approval.status,
                user_id=user_id,
            )

        # Valida que cognitive_plan existe
        if not approval.cognitive_plan:
            self.metrics.increment_republish_failures("no_cognitive_plan")
            raise ValueError(f"Plano nao possui cognitive_plan para republicar: {plan_id}")

        # Cria ApprovalResponse para republicacao
        response = ApprovalResponse(
            plan_id=plan_id,
            intent_id=approval.intent_id,
            decision="approved",
            approved_by=approval.approved_by or user_id,
            approved_at=approval.approved_at or datetime.now(timezone.utc),
            cognitive_plan=approval.cognitive_plan,
        )

        # Publica no Kafka
        try:
            await self.response_producer.send_approval_response(response)
        except Exception as e:
            self.metrics.increment_republish_failures("kafka_error")
            self.metrics.increment_republish_total("failure", force)
            logger.error("Erro ao publicar republicacao no Kafka", plan_id=plan_id, error=str(e))
            raise

        # Emite metricas de sucesso
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        self.metrics.increment_republish_total("success", force)
        self.metrics.observe_republish_duration(duration)
        self.metrics.increment_api_requests("republish", "200")

        logger.info(
            "Plano republicado com sucesso",
            plan_id=plan_id,
            intent_id=approval.intent_id,
            republished_by=user_id,
            original_approved_by=approval.approved_by,
            force=force,
            comments=comments,
            duration_seconds=duration,
            risk_band=getattr(approval, "risk_band", "unknown"),
        )

        return response

    async def revert_approval(
        self,
        plan_id: str,
        user_id: str,
        reason: str,
        comments: Optional[str] = None,
        ticket_id: Optional[str] = None,
    ) -> RevertResponse:
        """
        F4: Reverte uma aprovacao (para compensacao Saga)

        Altera o status de APPROVED para PENDING, permitindo que o plano
        seja reavaliado. Usado pelo padrao Saga quando execucoes
        subsequentes falham e precisam de compensacao.

        Args:
            plan_id: ID do plano cognitivo
            user_id: ID do usuario que esta fazendo a reversao
            reason: Motivo da reversao (obrigatorio)
            comments: Comentarios opcionais
            ticket_id: ID do ticket de compensacao

        Returns:
            RevertResponse com detalhes da reversao

        Raises:
            ValueError: Se plano nao encontrado ou nao esta aprovado
        """
        from src.models import RevertResponse

        start_time = datetime.now(timezone.utc)

        logger.info(
            "Revertendo aprovacao",
            plan_id=plan_id,
            user_id=user_id,
            reason=reason,
            ticket_id=ticket_id,
        )

        # Buscar aprovacao atual
        approval = await self.mongodb_client.get_approval_by_plan_id(plan_id)
        if not approval:
            error_msg = f"Plano {plan_id} nao encontrado"
            logger.warning("revert_approval_not_found", plan_id=plan_id)
            raise ValueError(error_msg)

        # Verificar se esta aprovado
        if approval.status != ApprovalStatus.APPROVED:
            error_msg = f"Plano {plan_id} nao esta aprovado (status: {approval.status})"
            logger.warning(
                "revert_approval_not_approved", plan_id=plan_id, current_status=approval.status
            )
            raise ValueError(error_msg)

        # Atualizar para PENDING
        previous_status = approval.status.value
        await self.mongodb_client.update_approval_decision(
            plan_id=plan_id,
            status=ApprovalStatus.PENDING,
            approved_by=None,
            approved_at=None,
            rejection_reason=f"REVERTED: {reason}",
            comments=comments,
        )

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        # Emitir metrica de reversao (se existir)
        if hasattr(self.metrics, "increment_revert_total"):
            self.metrics.increment_revert_total("success")

        logger.info(
            "Aprovacao revertida com sucesso",
            plan_id=plan_id,
            previous_status=previous_status,
            new_status="PENDING",
            reverted_by=user_id,
            reason=reason,
            ticket_id=ticket_id,
            duration_seconds=duration,
        )

        return RevertResponse(
            approval_id=approval.approval_id,
            plan_id=plan_id,
            previous_status=previous_status,
            new_status="PENDING",
            reverted_at=datetime.now(timezone.utc),
            reverted_by=user_id,
        )

    async def get_pending_approvals(
        self,
        limit: int = 50,
        offset: int = 0,
        risk_band: Optional[str] = None,
        is_destructive: Optional[bool] = None,
    ) -> list[ApprovalRequest]:
        """
        Lista aprovacoes pendentes com filtros

        Args:
            limit: Limite de resultados
            offset: Offset para paginacao
            risk_band: Filtro por banda de risco
            is_destructive: Filtro por destrutivo

        Returns:
            Lista de ApprovalRequest pendentes
        """
        filters = {}
        if risk_band:
            filters["risk_band"] = risk_band
        if is_destructive is not None:
            filters["is_destructive"] = is_destructive

        approvals = await self.mongodb_client.get_pending_approvals(
            limit=limit, offset=offset, filters=filters if filters else None
        )

        # Emite metrica de API
        self.metrics.increment_api_requests("pending", "200")

        return approvals

    async def get_approval_by_plan_id(self, plan_id: str) -> Optional[ApprovalRequest]:
        """
        Busca aprovacao por plan_id

        Args:
            plan_id: ID do plano

        Returns:
            ApprovalRequest ou None
        """
        return await self.mongodb_client.get_approval_by_plan_id(plan_id)

    async def get_approval_stats(self) -> ApprovalStats:
        """
        Retorna estatisticas de aprovacao

        Returns:
            ApprovalStats com contagens e metricas
        """
        stats = await self.mongodb_client.get_approval_stats()

        # Emite metrica de API
        self.metrics.increment_api_requests("stats", "200")

        return stats
