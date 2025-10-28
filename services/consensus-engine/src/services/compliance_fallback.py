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

    def check_compliance(
        self,
        cognitive_plan: Dict[str, Any],
        opinions: List[Dict[str, Any]],
        aggregated_confidence: float,
        aggregated_risk: float,
        divergence: float,
        is_unanimous: bool
    ) -> Tuple[bool, List[str]]:
        '''Verifica compliance e retorna violações

        Args:
            cognitive_plan: Plano cognitivo original
            opinions: Pareceres dos especialistas
            aggregated_confidence: Confiança agregada
            aggregated_risk: Risco agregado
            divergence: Divergência entre especialistas
            is_unanimous: Se houve unanimidade

        Returns:
            Tuple (está em compliance, lista de violações)
        '''
        violations = []

        # Regra 1: Confiança mínima obrigatória
        if aggregated_confidence < self.compliance_rules['min_confidence_score']:
            violations.append(
                f"Confiança agregada ({aggregated_confidence:.2f}) abaixo do mínimo "
                f"({self.compliance_rules['min_confidence_score']})"
            )

        # Regra 2: Divergência máxima permitida
        if divergence > self.compliance_rules['max_divergence']:
            violations.append(
                f"Divergência ({divergence:.2f}) acima do máximo "
                f"({self.compliance_rules['max_divergence']})"
            )

        # Regra 3: Planos de alto risco requerem unanimidade
        if aggregated_risk >= self.compliance_rules['critical_risk_threshold']:
            if self.compliance_rules['require_unanimous_for_critical'] and not is_unanimous:
                violations.append(
                    f"Plano crítico (risco {aggregated_risk:.2f}) requer unanimidade, "
                    f"mas não houve consenso unânime"
                )

        # Regra 4: Verificar se algum especialista rejeitou com alta confiança
        for opinion in opinions:
            if opinion['opinion']['recommendation'] == 'reject':
                if opinion['opinion']['confidence_score'] >= 0.9:
                    violations.append(
                        f"Especialista {opinion['specialist_type']} rejeitou com alta confiança "
                        f"({opinion['opinion']['confidence_score']:.2f})"
                    )

        # Regra 5: Verificar nível de segurança do plano original
        security_level = cognitive_plan.get('original_security_level', 'internal')
        if security_level in ['confidential', 'restricted']:
            if aggregated_confidence < 0.9:
                violations.append(
                    f"Plano com nível de segurança {security_level} requer confiança ≥0.9, "
                    f"mas obteve {aggregated_confidence:.2f}"
                )

        is_compliant = len(violations) == 0

        logger.info(
            'Compliance check',
            is_compliant=is_compliant,
            num_violations=len(violations),
            violations=violations
        )

        return is_compliant, violations

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
