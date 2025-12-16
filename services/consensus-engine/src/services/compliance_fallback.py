from typing import List, Dict, Any, Tuple
import structlog

logger = structlog.get_logger()


class ComplianceFallback:
    '''Fallback determinístico baseado em regras de compliance'''

    def __init__(self, config):
        self.config = config
        self.compliance_rules = self._load_compliance_rules()

    def _load_compliance_rules(self) -> Dict[str, Any]:
        '''Carrega regras de compliance

        MVP: Regras hardcoded
        Futuro: Carregar de OPA/Rego ou Knowledge Graph
        '''
        return {
            'min_confidence_score': self.config.min_confidence_score,
            'max_divergence': self.config.max_divergence_threshold,
            'high_risk_threshold': self.config.high_risk_threshold,
            'critical_risk_threshold': self.config.critical_risk_threshold,
            'require_unanimous_for_critical': self.config.require_unanimous_for_critical
        }

    def _detect_degraded_specialists(
        self,
        opinions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Detecta specialists usando fallbacks heurísticos ao invés de modelos ML.

        Um specialist é considerado degradado quando:
        1. metadata['model_source'] != 'ml_model' (indica fallback)
        2. explainability['method'] in ['heuristic', 'rule_based']
        3. confidence_score < 0.1 (indica heurística não calibrada)

        Args:
            opinions: Lista de pareceres dos especialistas

        Returns:
            Dict com:
            - degraded_count: Número de specialists degradados
            - degraded_specialists: Lista de tipos degradados
            - degradation_rate: Taxa de degradação (0.0-1.0)
            - health_status: 'healthy' | 'partially_degraded' | 'severely_degraded'
        """
        degraded_specialists = []

        for opinion in opinions:
            specialist_type = opinion['specialist_type']
            op = opinion['opinion']

            metadata = op.get('metadata', {})
            model_source = metadata.get('model_source', 'unknown')

            explainability = op.get('explainability', {})
            explain_method = explainability.get('method', 'unknown')

            confidence = op.get('confidence_score', 1.0)

            is_degraded = (
                model_source in ['heuristics', 'semantic_pipeline', 'unknown'] or
                explain_method in ['heuristic', 'rule_based', 'unknown'] or
                confidence < 0.1
            )

            if is_degraded:
                degraded_specialists.append(specialist_type)
                logger.warning(
                    'Specialist degraded - using fallback',
                    specialist_type=specialist_type,
                    model_source=model_source,
                    explain_method=explain_method,
                    confidence=confidence
                )

        degraded_count = len(degraded_specialists)
        total_specialists = len(opinions)
        degradation_rate = degraded_count / total_specialists if total_specialists > 0 else 0.0

        if degraded_count == 0:
            health_status = 'healthy'
        elif degraded_count <= 2:
            health_status = 'partially_degraded'
        else:
            health_status = 'severely_degraded'

        result = {
            'degraded_count': degraded_count,
            'degraded_specialists': degraded_specialists,
            'degradation_rate': degradation_rate,
            'health_status': health_status
        }

        logger.info(
            'Specialist health detection',
            degraded_count=degraded_count,
            total_specialists=total_specialists,
            degradation_rate=f"{degradation_rate:.1%}",
            health_status=health_status,
            degraded_list=degraded_specialists
        )

        return result

    def _calculate_adaptive_thresholds(
        self,
        degradation_info: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        Calcula thresholds adaptativos baseado no estado de saúde dos modelos.

        Estratégia de ajuste:
        - healthy (0 degraded): Thresholds estritos para máxima qualidade
        - partially_degraded (1-2 degraded): Thresholds moderados
        - severely_degraded (3+ degraded): Thresholds relaxados para evitar bloqueio total
        """
        health_status = degradation_info['health_status']
        degraded_count = degradation_info['degraded_count']
        degraded_list = degradation_info['degraded_specialists']

        base_confidence = self.compliance_rules['min_confidence_score']
        base_divergence = self.compliance_rules['max_divergence']

        if health_status == 'healthy':
            adjusted_confidence = max(0.70, base_confidence)
            adjusted_divergence = min(0.15, base_divergence)
            adjustment_reason = 'All models healthy - using strict thresholds for maximum quality'

        elif health_status == 'partially_degraded':
            adjusted_confidence = base_confidence
            adjusted_divergence = base_divergence
            adjustment_reason = f'{degraded_count} model(s) degraded ({", ".join(degraded_list)}) - using base thresholds'

        else:  # severely_degraded
            adjusted_confidence = 0.50
            adjusted_divergence = 0.35
            adjustment_reason = f'{degraded_count} models degraded ({", ".join(degraded_list)}) - using relaxed thresholds to prevent total blockage'

        result = {
            'min_confidence': adjusted_confidence,
            'max_divergence': adjusted_divergence,
            'adjustment_reason': adjustment_reason,
            'base_confidence': base_confidence,
            'base_divergence': base_divergence,
            'health_status': health_status,
            'degraded_count': degraded_count
        }

        logger.info(
            'Adaptive thresholds calculated',
            health_status=health_status,
            degraded_count=degraded_count,
            base_confidence=base_confidence,
            adjusted_confidence=adjusted_confidence,
            base_divergence=base_divergence,
            adjusted_divergence=adjusted_divergence,
            adjustment_reason=adjustment_reason
        )

        return result

    def check_compliance(
        self,
        cognitive_plan: Dict[str, Any],
        opinions: List[Dict[str, Any]],
        aggregated_confidence: float,
        aggregated_risk: float,
        divergence: float,
        is_unanimous: bool
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Verifica compliance com thresholds adaptativos baseados em saúde dos modelos.

        Fluxo:
        1. Detecta specialists degradados analisando metadata das opiniões
        2. Calcule thresholds adaptativos baseado no nível de degradação
        3. Aplica regras de compliance com thresholds ajustados
        4. Retorna violações (se houver) com contexto de ajuste
        """
        violations = []

        degradation_info = self._detect_degraded_specialists(opinions)
        adaptive_thresholds = self._calculate_adaptive_thresholds(degradation_info)

        min_confidence = adaptive_thresholds['min_confidence']
        max_divergence = adaptive_thresholds['max_divergence']
        adjustment_reason = adaptive_thresholds['adjustment_reason']

        if aggregated_confidence < min_confidence:
            violations.append(
                f"Confiança agregada ({aggregated_confidence:.2f}) abaixo do mínimo adaptativo "
                f"({min_confidence:.2f}) [base: {adaptive_thresholds['base_confidence']:.2f}, "
                f"ajustado: {adjustment_reason}]"
            )

        if divergence > max_divergence:
            violations.append(
                f"Divergência ({divergence:.2f}) acima do máximo adaptativo "
                f"({max_divergence:.2f}) [base: {adaptive_thresholds['base_divergence']:.2f}, "
                f"ajustado: {adjustment_reason}]"
            )

        if aggregated_risk >= self.compliance_rules['critical_risk_threshold']:
            if self.compliance_rules['require_unanimous_for_critical'] and not is_unanimous:
                violations.append(
                    f"Plano crítico (risco {aggregated_risk:.2f}) requer unanimidade, "
                    f"mas não houve consenso unânime"
                )

        rejection_threshold = 0.9 if degradation_info['health_status'] == 'healthy' else 0.85

        for opinion in opinions:
            if opinion['opinion']['recommendation'] == 'reject':
                opinion_confidence = opinion['opinion']['confidence_score']
                if opinion_confidence >= rejection_threshold:
                    violations.append(
                        f"Especialista {opinion['specialist_type']} rejeitou com alta confiança "
                        f"({opinion_confidence:.2f}, threshold: {rejection_threshold:.2f})"
                    )

        security_level = cognitive_plan.get('original_security_level', 'internal')
        if security_level in ['confidential', 'restricted']:
            security_confidence_threshold = 0.9
            if aggregated_confidence < security_confidence_threshold:
                violations.append(
                    f"Plano com nível de segurança {security_level} requer confiança ≥{security_confidence_threshold:.2f}, "
                    f"mas obteve {aggregated_confidence:.2f} (thresholds adaptativos não aplicam a planos de alta segurança)"
                )

        is_compliant = len(violations) == 0

        logger.info(
            'Compliance check with adaptive thresholds',
            is_compliant=is_compliant,
            num_violations=len(violations),
            violations=violations,
            adaptive_thresholds=adaptive_thresholds,
            degradation_info=degradation_info
        )

        return is_compliant, violations, adaptive_thresholds

    def apply_fallback_decision(
        self,
        cognitive_plan: Dict[str, Any],
        opinions: List[Dict[str, Any]],
        violations: List[str]
    ) -> str:
        '''Aplica decisão determinística de fallback

        Quando compliance falha, aplicar regras determinísticas:
        - Se divergência alta → review_required
        - Se confiança baixa → review_required
        - Se risco crítico sem unanimidade → reject
        - Se rejeição com alta confiança → reject
        '''
        # Analisar violações
        has_high_divergence = any('Divergência' in v for v in violations)
        has_low_confidence = any('Confiança agregada' in v for v in violations)
        has_critical_risk = any('crítico' in v for v in violations)
        has_high_confidence_reject = any('rejeitou com alta confiança' in v for v in violations)

        # Aplicar regras determinísticas
        if has_high_confidence_reject:
            decision = 'reject'
            reason = 'Rejeição com alta confiança de especialista'
        elif has_critical_risk:
            decision = 'reject'
            reason = 'Risco crítico sem unanimidade'
        elif has_high_divergence or has_low_confidence:
            decision = 'review_required'
            reason = 'Divergência alta ou confiança baixa'
        else:
            decision = 'review_required'
            reason = 'Violação de compliance genérica'

        logger.warning(
            'Fallback determinístico aplicado',
            plan_id=cognitive_plan['plan_id'],
            decision=decision,
            reason=reason,
            violations=violations
        )

        return decision
