"""Orquestrador de incidentes que coordena todo o fluxo E1-E6"""
from typing import Dict, Any, Optional, List
import structlog
from datetime import datetime, timezone

logger = structlog.get_logger()


class IncidentOrchestrator:
    """Orquestra fluxo completo de detecção até validação de SLA (E1-E6)"""

    def __init__(
        self,
        threat_detector,
        incident_classifier,
        policy_enforcer,
        remediation_coordinator,
        mongodb_client=None,
        kafka_producer=None,
        prometheus_client=None,
        itsm_client=None
    ):
        self.threat_detector = threat_detector
        self.incident_classifier = incident_classifier
        self.policy_enforcer = policy_enforcer
        self.remediation_coordinator = remediation_coordinator
        self.mongodb = mongodb_client
        self.kafka_producer = kafka_producer
        self.prometheus_client = prometheus_client
        self.itsm_client = itsm_client
        self.sla_targets = self._initialize_sla_targets()

    def _initialize_sla_targets(self) -> Dict[str, float]:
        """Inicializa targets de SLA conforme documentação"""
        return {
            "mttd_seconds": 15.0,  # Mean Time To Detect
            "mttr_seconds": 90.0,  # Mean Time To Recover
            "auto_correction_rate": 0.85,  # Taxa de autocorreção >= 85%
        }

    async def process_incident_flow(
        self,
        event: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Processa fluxo completo E1→E6 de forma orquestrada

        Fluxo:
        E1: Detectar anomalia (ThreatDetector)
        E2: Classificar severidade (IncidentClassifier)
        E3: Selecionar playbook e executar políticas (PolicyEnforcer)
        E4: Executar ações de autocura (RemediationCoordinator)
        E5: Validar restauração de SLA
        E6: Documentar lições aprendidas

        Args:
            event: Evento de segurança ou telemetria
            context: Contexto adicional

        Returns:
            Dict com resultado completo do fluxo
        """
        flow_start_time = datetime.now(timezone.utc)

        try:
            logger.info(
                "incident_orchestrator.flow_started",
                event_type=event.get("type"),
                event_id=event.get("event_id")
            )

            # E1: Detectar anomalia
            anomaly = await self._e1_detect_anomaly(event)
            if not anomaly:
                # Nenhuma anomalia detectada
                return self._create_no_incident_result(event, flow_start_time)

            # E2: Classificar severidade
            incident = await self._e2_classify_severity(anomaly, context)

            # E3: Enforçar políticas (OPA/Istio)
            enforcement_result = await self._e3_enforce_policies(incident)

            # E4: Executar playbooks de autocura
            remediation_result = await self._e4_execute_remediation(
                incident, enforcement_result
            )

            # E5: Validar restauração de SLA
            sla_validation = await self._e5_validate_sla_restoration(
                incident, remediation_result, flow_start_time
            )

            # E6: Documentar lições aprendidas
            lessons_learned = await self._e6_document_lessons(
                incident, enforcement_result, remediation_result, sla_validation
            )

            # Consolidar resultado final
            final_result = self._create_final_result(
                event,
                anomaly,
                incident,
                enforcement_result,
                remediation_result,
                sla_validation,
                lessons_learned,
                flow_start_time
            )

            # Persistir resultado
            await self._persist_incident_outcome(final_result)

            # Publicar evento de conclusão
            await self._publish_incident_outcome(final_result)

            logger.info(
                "incident_orchestrator.flow_completed",
                incident_id=incident.get("incident_id"),
                duration_ms=final_result.get("duration_ms"),
                sla_met=sla_validation.get("sla_met")
            )

            return final_result

        except Exception as e:
            logger.error(
                "incident_orchestrator.flow_failed",
                error=str(e),
                event_id=event.get("event_id")
            )
            raise

    async def _e1_detect_anomaly(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """E1: Detectar anomalia (Thresholds adaptativos)"""
        logger.debug("incident_orchestrator.e1_detecting", event_id=event.get("event_id"))

        detection_start = datetime.now(timezone.utc)

        anomaly = await self.threat_detector.detect_anomaly(event)

        detection_time = (datetime.now(timezone.utc) - detection_start).total_seconds()

        if anomaly:
            logger.info(
                "incident_orchestrator.e1_detected",
                threat_type=anomaly.get("threat_type"),
                detection_time_s=detection_time
            )

            # Verificar MTTD
            if detection_time > self.sla_targets["mttd_seconds"]:
                logger.warning(
                    "incident_orchestrator.mttd_exceeded",
                    detection_time_s=detection_time,
                    target_s=self.sla_targets["mttd_seconds"]
                )

        return anomaly

    async def _e2_classify_severity(
        self, anomaly: Dict[str, Any], context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """E2: Classificar severidade (Classificação mapeada a runbooks)"""
        logger.debug(
            "incident_orchestrator.e2_classifying",
            threat_type=anomaly.get("threat_type")
        )

        incident = await self.incident_classifier.classify_incident(anomaly, context)

        logger.info(
            "incident_orchestrator.e2_classified",
            incident_id=incident.get("incident_id"),
            severity=incident.get("severity"),
            runbook_id=incident.get("runbook_id")
        )

        # E2: Severidade desconhecida → acionar duty engineer
        if incident.get("requires_human_review"):
            logger.warning(
                "incident_orchestrator.e2_human_review_required",
                incident_id=incident.get("incident_id")
            )

        return incident

    async def _e3_enforce_policies(
        self, incident: Dict[str, Any]
    ) -> Dict[str, Any]:
        """E3: Selecionar playbook e executar políticas de enforcement (OPA/Istio)"""
        logger.debug(
            "incident_orchestrator.e3_enforcing",
            incident_id=incident.get("incident_id")
        )

        enforcement_result = await self.policy_enforcer.enforce_policy(incident)

        logger.info(
            "incident_orchestrator.e3_enforced",
            incident_id=incident.get("incident_id"),
            success=enforcement_result.get("success")
        )

        # E3: Playbook inexistente → criar stub e notificar engenharia
        if enforcement_result.get("requires_engineering_review"):
            logger.warning(
                "incident_orchestrator.e3_stub_playbook_created",
                incident_id=incident.get("incident_id")
            )

        return enforcement_result

    async def _e4_execute_remediation(
        self, incident: Dict[str, Any], enforcement_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """E4: Executar ações de autocura (Sequenciar ações atomicamente)"""
        logger.debug(
            "incident_orchestrator.e4_remediating",
            incident_id=incident.get("incident_id")
        )

        remediation_result = await self.remediation_coordinator.coordinate_remediation(
            incident, enforcement_result
        )

        logger.info(
            "incident_orchestrator.e4_remediated",
            remediation_id=remediation_result.get("remediation_id"),
            status=remediation_result.get("status")
        )

        # E4: Falha > 2 tentativas → escalar para humano
        if remediation_result.get("requires_human_intervention"):
            logger.error(
                "incident_orchestrator.e4_human_intervention_required",
                remediation_id=remediation_result.get("remediation_id")
            )

        return remediation_result

    async def _e5_validate_sla_restoration(
        self,
        incident: Dict[str, Any],
        remediation_result: Dict[str, Any],
        flow_start_time: datetime
    ) -> Dict[str, Any]:
        """E5: Validar restauração de SLA (Confirmar retorno ao SLA)"""
        logger.debug(
            "incident_orchestrator.e5_validating_sla",
            incident_id=incident.get("incident_id")
        )

        # Calcular MTTR
        recovery_time = (datetime.now(timezone.utc) - flow_start_time).total_seconds()

        # Verificar se SLA foi restaurado
        sla_met = True
        issues = []
        prometheus_metrics = {}

        # Verificar MTTR
        if recovery_time > self.sla_targets["mttr_seconds"]:
            sla_met = False
            issues.append(f"MTTR exceeded: {recovery_time:.2f}s > {self.sla_targets['mttr_seconds']}s")

        # Verificar se remediação foi bem-sucedida
        if remediation_result.get("status") != "completed":
            sla_met = False
            issues.append(f"Remediation not completed: {remediation_result.get('status')}")

        # Validar SLA com Prometheus se disponível
        if self.prometheus_client:
            try:
                affected_service = self._extract_affected_service(incident)
                if affected_service:
                    logger.info(
                        "incident_orchestrator.validating_prometheus_sla",
                        service=affected_service
                    )

                    # Validar restauração de métricas de SLA
                    sla_validation = await self.prometheus_client.validate_sla_restoration(
                        service=affected_service,
                        sla_targets={
                            "min_success_rate": 99.9,
                            "max_latency_p99": 0.5,
                            "max_error_rate": 0.1
                        }
                    )

                    prometheus_metrics = sla_validation.get("metrics", {})

                    if not sla_validation.get("sla_restored"):
                        sla_met = False
                        for violation in sla_validation.get("violations", []):
                            issues.append(
                                f"{violation['metric']}: {violation['value']:.2f} (target: {violation['target']})"
                            )

                    logger.info(
                        "incident_orchestrator.prometheus_sla_validated",
                        service=affected_service,
                        sla_restored=sla_validation.get("sla_restored"),
                        metrics=prometheus_metrics
                    )

            except Exception as e:
                logger.error(
                    "incident_orchestrator.prometheus_validation_failed",
                    error=str(e)
                )
                issues.append(f"Prometheus validation error: {str(e)}")

        # E5: SLA não recuperado → abrir incidente crítico
        if not sla_met:
            logger.error(
                "incident_orchestrator.e5_sla_not_restored",
                incident_id=incident.get("incident_id"),
                recovery_time_s=recovery_time,
                issues=issues
            )
            await self._open_critical_incident(incident, issues)

        validation = {
            "sla_met": sla_met,
            "recovery_time_s": recovery_time,
            "mttr_target_s": self.sla_targets["mttr_seconds"],
            "prometheus_metrics": prometheus_metrics,
            "issues": issues,
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "incident_orchestrator.e5_validated",
            incident_id=incident.get("incident_id"),
            sla_met=sla_met,
            recovery_time_s=recovery_time,
            prometheus_validated=bool(prometheus_metrics)
        )

        return validation

    def _extract_affected_service(self, incident: Dict[str, Any]) -> Optional[str]:
        """Extrai nome do serviço afetado do incidente"""
        resources = incident.get("affected_resources", [])
        if resources:
            # Assumir formato: namespace/kind/name
            first_resource = resources[0]
            parts = first_resource.split("/")
            if len(parts) >= 3:
                return parts[2]  # Nome do recurso (deployment/service)

        # Fallback: tentar extrair de metadados
        return incident.get("service_name") or incident.get("resource_name")

    async def _e6_document_lessons(
        self,
        incident: Dict[str, Any],
        enforcement_result: Dict[str, Any],
        remediation_result: Dict[str, Any],
        sla_validation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """E6: Documentar licoes aprendidas (Registro em ate 4h)"""
        logger.debug(
            "incident_orchestrator.e6_documenting",
            incident_id=incident.get("incident_id")
        )

        lessons = {
            "incident_id": incident.get("incident_id"),
            "threat_type": incident.get("threat_type"),
            "severity": incident.get("severity"),
            "runbook_id": incident.get("runbook_id"),
            "summary": self._generate_incident_summary(
                incident, enforcement_result, remediation_result, sla_validation
            ),
            "root_cause": self._analyze_root_cause(incident),
            "actions_taken": self._summarize_actions(enforcement_result, remediation_result),
            "sla_performance": {
                "met": sla_validation.get("sla_met"),
                "recovery_time_s": sla_validation.get("recovery_time_s"),
            },
            "recommendations": self._generate_recommendations(
                incident, sla_validation
            ),
            "documented_at": datetime.now(timezone.utc).isoformat(),
        }

        # Persistir no Knowledge Base (colecao de post-mortems)
        if self.mongodb and self.mongodb.postmortems_collection:
            try:
                await self.mongodb.postmortems_collection.insert_one(lessons)
                logger.info(
                    "incident_orchestrator.e6_documented",
                    incident_id=incident.get("incident_id"),
                    collection="incident_postmortems"
                )
            except Exception as e:
                # E6: Atraso -> alerta compliance
                logger.error(
                    "incident_orchestrator.e6_documentation_delayed",
                    incident_id=incident.get("incident_id"),
                    error=str(e)
                )
                # Publicar alerta de compliance
                await self._publish_compliance_alert(incident.get("incident_id"), str(e))

        return lessons

    async def _publish_compliance_alert(self, incident_id: str, error: str):
        """Publica alerta de compliance quando documentacao atrasa"""
        if self.kafka_producer:
            try:
                alert = {
                    "type": "COMPLIANCE_VIOLATION",
                    "incident_id": incident_id,
                    "violation": "E6_DOCUMENTATION_DELAYED",
                    "error": error,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                # Tentar publicar via metodo generico do producer
                if hasattr(self.kafka_producer, 'publish_compliance_alert'):
                    await self.kafka_producer.publish_compliance_alert(alert)
                else:
                    logger.warning(
                        "incident_orchestrator.compliance_alert_method_not_found",
                        incident_id=incident_id
                    )
            except Exception as e:
                logger.error(
                    "incident_orchestrator.compliance_alert_failed",
                    incident_id=incident_id,
                    error=str(e)
                )

    def _generate_incident_summary(
        self,
        incident: Dict[str, Any],
        enforcement_result: Dict[str, Any],
        remediation_result: Dict[str, Any],
        sla_validation: Dict[str, Any]
    ) -> str:
        """Gera resumo do incidente"""
        summary = (
            f"Incidente {incident.get('incident_id')} detectado: "
            f"{incident.get('threat_type')} com severidade {incident.get('severity')}. "
            f"Playbook {incident.get('runbook_id')} executado. "
            f"Remediação {remediation_result.get('status')}. "
            f"SLA {'restaurado' if sla_validation.get('sla_met') else 'NÃO restaurado'}."
        )
        return summary

    def _analyze_root_cause(self, incident: Dict[str, Any]) -> str:
        """Analisa causa raiz (placeholder)"""
        # TODO: Análise mais sofisticada com ML/correlação
        return f"Threat type: {incident.get('threat_type')}"

    def _summarize_actions(
        self,
        enforcement_result: Dict[str, Any],
        remediation_result: Dict[str, Any]
    ) -> List[str]:
        """Sumariza ações tomadas"""
        actions = []

        # Ações de enforcement
        for action in enforcement_result.get("actions", []):
            actions.append(f"Enforcement: {action.get('action')}")

        # Ações de remediação
        for action in remediation_result.get("actions", []):
            actions.append(f"Remediation: {action.get('action_type')}")

        return actions

    def _generate_recommendations(
        self, incident: Dict[str, Any], sla_validation: Dict[str, Any]
    ) -> List[str]:
        """Gera recomendações"""
        recommendations = []

        if not sla_validation.get("sla_met"):
            recommendations.append("Revisar playbook para melhorar MTTR")
            recommendations.append("Considerar automação adicional")

        if incident.get("requires_human_review"):
            recommendations.append("Melhorar regras de detecção para reduzir falsos positivos")

        return recommendations

    async def _open_critical_incident(
        self, incident: Dict[str, Any], issues: List[str]
    ):
        """
        E5: Abre incidente crítico quando SLA não é restaurado.

        Integra com sistema ITSM (ServiceNow, Jira, PagerDuty, etc.)
        para criar ticket de alta prioridade.

        Args:
            incident: Incidente original
            issues: Lista de problemas detectados
        """
        original_incident_id = incident.get("incident_id")
        severity = incident.get("severity", "high")
        threat_type = incident.get("threat_type", "unknown")

        logger.error(
            "incident_orchestrator.opening_critical_incident",
            original_incident_id=original_incident_id,
            issues=issues,
            severity=severity
        )

        # Construir detalhes do incidente crítico
        critical_incident = {
            "type": "CRITICAL_SLA_BREACH",
            "original_incident_id": original_incident_id,
            "issues": issues,
            "severity": severity,
            "threat_type": threat_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Usar itsm_client injetado via construtor
        if self.itsm_client and self.itsm_client.is_healthy():
            try:
                # Construir título e descrição
                title = f"Critical SLA Breach - {original_incident_id}"
                description = (
                    f"Automatic remediation failed to restore SLA for incident {original_incident_id}.\n\n"
                    f"Threat Type: {threat_type}\n"
                    f"Severity: {severity}\n"
                    f"Time: {critical_incident['created_at']}\n\n"
                    f"Issues:\n" + "\n".join(f"- {issue}" for issue in issues)
                )

                # Criar incidente no ITSM
                result = await self.itsm_client.create_incident(
                    title=title,
                    description=description,
                    priority="critical",
                    category="sla_breach",
                    original_incident_id=original_incident_id,
                    issues=issues,
                    metadata={
                        "threat_type": threat_type,
                        "severity": severity,
                        "source": "guard-agents"
                    }
                )

                if result.get("success"):
                    ticket_id = result.get("ticket_id")
                    critical_incident["itsm_ticket_id"] = ticket_id
                    critical_incident["itsm_type"] = result.get("itsm_type")

                    logger.info(
                        "incident_orchestrator.itsm_ticket_created",
                        ticket_id=ticket_id,
                        original_incident_id=original_incident_id
                    )
                else:
                    logger.error(
                        "incident_orchestrator.itsm_creation_failed",
                        original_incident_id=original_incident_id,
                        error=result.get("error")
                    )
                    critical_incident["itsm_error"] = result.get("error")

            except Exception as e:
                logger.error(
                    "incident_orchestrator.itsm_error",
                    original_incident_id=original_incident_id,
                    error=str(e)
                )
                critical_incident["itsm_error"] = str(e)
        else:
            logger.warning(
                "incident_orchestrator.itsm_not_available",
                action="open_critical_incident"
            )
            critical_incident["itsm_status"] = "not_available"

        # Persistir incidente crítico no MongoDB
        if self.mongodb and hasattr(self.mongodb, 'critical_incidents_collection'):
            try:
                if self.mongodb.critical_incidents_collection:
                    await self.mongodb.critical_incidents_collection.insert_one(critical_incident)
                    logger.info(
                        "incident_orchestrator.critical_incident_persisted",
                        original_incident_id=original_incident_id
                    )
            except Exception as e:
                logger.error(
                    "incident_orchestrator.persist_critical_incident_failed",
                    error=str(e)
                )

        # Publicar evento de incidente crítico no Kafka
        if self.kafka_producer:
            try:
                if hasattr(self.kafka_producer, 'publish_critical_incident'):
                    await self.kafka_producer.publish_critical_incident(critical_incident)
                    logger.info(
                        "incident_orchestrator.critical_incident_published",
                        original_incident_id=original_incident_id
                    )
            except Exception as e:
                logger.error(
                    "incident_orchestrator.publish_critical_incident_failed",
                    error=str(e)
                )

    def _create_no_incident_result(
        self, event: Dict[str, Any], flow_start_time: datetime
    ) -> Dict[str, Any]:
        """Cria resultado quando não há incidente"""
        duration_ms = (datetime.now(timezone.utc) - flow_start_time).total_seconds() * 1000

        return {
            "incident_detected": False,
            "event_id": event.get("event_id"),
            "duration_ms": duration_ms,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

    def _create_final_result(
        self,
        event: Dict[str, Any],
        anomaly: Dict[str, Any],
        incident: Dict[str, Any],
        enforcement_result: Dict[str, Any],
        remediation_result: Dict[str, Any],
        sla_validation: Dict[str, Any],
        lessons_learned: Dict[str, Any],
        flow_start_time: datetime
    ) -> Dict[str, Any]:
        """Cria resultado final do fluxo completo"""
        duration_ms = (datetime.now(timezone.utc) - flow_start_time).total_seconds() * 1000

        return {
            "incident_id": incident.get("incident_id"),
            "event_id": event.get("event_id"),
            "flow": "E1-E6_complete",
            "e1_anomaly": {
                "threat_type": anomaly.get("threat_type"),
                "severity": anomaly.get("severity"),
                "confidence": anomaly.get("confidence"),
            },
            "e2_classification": {
                "severity": incident.get("severity"),
                "runbook_id": incident.get("runbook_id"),
                "priority": incident.get("priority"),
            },
            "e3_enforcement": {
                "success": enforcement_result.get("success"),
                "actions_count": len(enforcement_result.get("actions", [])),
            },
            "e4_remediation": {
                "status": remediation_result.get("status"),
                "remediation_id": remediation_result.get("remediation_id"),
            },
            "e5_sla_validation": sla_validation,
            "e6_lessons_learned": lessons_learned,
            "duration_ms": duration_ms,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _persist_incident_outcome(self, result: Dict[str, Any]):
        """Persiste resultado final"""
        if self.mongodb and self.mongodb.incidents_collection:
            try:
                await self.mongodb.incidents_collection.update_one(
                    {"incident_id": result.get("incident_id")},
                    {"$set": {"final_outcome": result}},
                    upsert=True
                )
            except Exception as e:
                logger.error(
                    "incident_orchestrator.persist_failed",
                    incident_id=result.get("incident_id"),
                    error=str(e)
                )

    async def _publish_incident_outcome(self, result: Dict[str, Any]):
        """
        Publica evento de conclusão do fluxo E1-E6 no Kafka.

        Args:
            result: Resultado completo do fluxo de incidentes
        """
        incident_id = result.get("incident_id")

        if not self.kafka_producer:
            logger.warning(
                "incident_orchestrator.no_kafka_producer",
                incident_id=incident_id
            )
            return

        try:
            # Usar publish_remediation_result do RemediationProducer se disponível
            if hasattr(self.kafka_producer, 'publish_remediation_result'):
                published = await self.kafka_producer.publish_remediation_result(
                    remediation_id=incident_id,
                    result=result
                )

                if published:
                    logger.info(
                        "incident_orchestrator.outcome_published",
                        incident_id=incident_id,
                        flow=result.get("flow"),
                        sla_met=result.get("e5_sla_validation", {}).get("sla_met")
                    )
                else:
                    logger.error(
                        "incident_orchestrator.publish_failed",
                        incident_id=incident_id,
                        reason="Producer returned False"
                    )
            else:
                # Fallback: tentar método genérico send
                if hasattr(self.kafka_producer, 'send'):
                    await self.kafka_producer.send(
                        topic="incident-outcomes",
                        value=result
                    )
                    logger.info(
                        "incident_orchestrator.outcome_published_fallback",
                        incident_id=incident_id
                    )
                else:
                    logger.warning(
                        "incident_orchestrator.no_publish_method",
                        incident_id=incident_id
                    )

        except Exception as e:
            logger.error(
                "incident_orchestrator.publish_error",
                incident_id=incident_id,
                error=str(e)
            )
