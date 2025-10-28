# Camada de Resiliência e Segurança – Agentes

## Visão Geral
- Fecha o ciclo intenção→execução→feedback, garantindo observabilidade, autocura e cumprimento de políticas de segurança.
- Atua preventivamente (detecção) e reativamente (playbooks) para manter SLAs e governança.
- Referências: `docs/observability/services/autocura.md`, `docs/observability/architecture.md`, `documento-04-seguranca-governanca-neural-hive-mind.md`.
- **Natureza Híbrida**: os agentes combinam modelos de anomalia, ML supervisionado e LLMs (para relatórios) com motores SOAR, playbooks Terraform/Ansible e políticas OPA. A resposta depende de automações determinísticas e governança, não apenas interação com modelos linguísticos.

## Guardiões (Guard Agents)
- **Características**: sentinelas que monitoram ameaças, compliance e desvios operacionais continuamente.
- **Tecnologia/IA**: ML supervisionado/autoencoders para anomalias; CEP/KSQL para correlação; verificações OPA; enforcement automático com service mesh; classificadores de severidade.
- **Ferramentas/Stack**: OPA/Gatekeeper, Falco, Istio/WAF, Splunk ou Elastic SIEM, Alertmanager, SOAR (StackStorm/Rundeck), integrações IAM (Keycloak) para revogação imediata.
- **Responsabilidades**: acionar playbooks de autocura, bloquear execuções suspeitas, isolar componentes, notificar Rainha/Analistas.
- **Integrações**: Autocura, Orquestração, Service Mesh, Mecanismo de Feromônios, ledger de auditoria.
- **Métricas e Telemetria**: MTTD, `% incidentes autocorrigidos`, taxa de falsos positivos; logs assinados `incident_id`, spans Autocura.
- **Riscos**: excesso de alertas gera fadiga; falhas de configuração OPA; dependência de telemetria.

## Motor de Autocura & Runbooks Automatizados
- **Características**: plataforma que executa respostas automatizadas com telemetria end-to-end e playbooks declarativos.
- **Tecnologia/IA**: modelos de previsão de incidentes; classificação assistida por LLMs para relatórios; execução de playbooks via Terraform/Ansible/Argo; reinforcement learning para recomendar ações; bibliotecas GitOps com testes de caos.
- **Ferramentas/Stack**: Terraform, Ansible, Argo Workflows, StackStorm/Rundeck, ChaosMesh/Litmus, GitOps (ArgoCD/Flux), integrações PagerDuty/Slack.
- **Responsabilidades**: coordenar MTTR <90 s, registrar ações no ledger, retroalimentar Otimizadores e metacognição, manter compliance e auditorias.
- **Integrações**: Guardiões, Orquestração, Executores, ledger de auditoria, dashboards de governança.
- **Métricas e Telemetria**: MTTR, taxa de autocorreção, cobertura de playbooks, `remediation_success_rate`; logs assinados, relatórios pós-incident.
- **Riscos**: playbooks desatualizados, permissões excessivas, dependência da stack de observabilidade.

## Indicadores de Camada
| Indicador | Agente | Observações |
| --- | --- | --- |
| MTTD < 15s | Guardiões | Necessário CEP/telemetria consistente |
| MTTR < 90s | Motor de Autocura | Depende da eficácia dos playbooks |
| Taxa de autocorreção ≥ X% | Guardiões + Autocura | Medir em incidentes por severidade |

## Referências Cruzadas
- `docs/observability/services/agentes.md`
- `docs/observability/services/autocura.md`
- `documento-04-seguranca-governanca-neural-hive-mind.md`
