# Gateway – Visão Detalhada

## Papel no Pipeline
- Porta de entrada do organismo digital, recebendo requisições de APIs, portais, chatbots e dispositivos edge antes de normalizá-las em `Intent Envelopes` canônicos.
- Executa pré-validação de esquema, identificação de canal/cenário e aplica circuit breakers antes de publicar no barramento (Kafka Strimzi) ou encaminhar para captura de intenção, conforme Fluxo A (documento-06, Seção 4).

## Componentes Principais
- **Ingestão Multicanal**: proxies Envoy/NGINX, WebSockets, WebRTC, conectores MQTT para edge.
- **Normalização**: conversores JSON-LD ↔ Avro com schema registry (ADR-0005).
- **Policies na Borda**: integração com OPA/Gatekeeper para validação de payload e rate limiting contextual.
- **Observabilidade Local**: sidecars OTel auto-instrumentados, métricas padrão `neural_hive_gateway_*` e exporters de logs estruturados.

## Arquitetura e Tecnologias
- Implantado sobre Kubernetes/EKS com Istio sidecar para mTLS STRICT (ADR-0002) e key rotation SPIFFE.
- Usa Redis Operator como cache contextual de curto prazo e integra com AWS ECR para imagens assinadas (ADR-0003, ADR-0008).
- Edge gateways podem operar degradados com sincronização eventual para topologias federada e edge-augmented (documento-02, Seção 3).

## Integração com IA (ML/LLM)
- Aciona pipelines de ASR/TTS (Whisper, Twilio) e NLU pré-treinadas para rotular intenção e confiança inicial.
- Invoca modelos embarcados para anonimização PII e detecção de idioma antes de trafegar dados sensíveis.
- Propaga `intent_confidence` e `requires_manual_validation` para o pipeline cognitivo e métrica de gating (VERIFICACOES_IMPLEMENTADAS.md, item 2).

## Integrações Operacionais
- Publica eventos em tópicos particionados por domínio (`intentions.business`, `intentions.technical`) com exactly-once (ADR-0004).
- Autenticação via Keycloak OIDC + mTLS híbrido, com tokens de curta duração e claims customizados (ADR-0009).
- Registra ativos no catálogo CRD `ApiAsset`, garantindo classificação de dados e SLA (ADR-0010).

## Escalabilidade e Resiliência
- HPA baseado em p95 de latência e throughput por canal, com suporte a topologia multi-região.
- CDN + edge caching para canais públicos; fallback offline-first para agentes locais.
- Circuit breakers interagem com Orquestração para redirecionar carga quando thresholds são atingidos.

## Segurança
- Zero-trust: autenticação multifator, ABAC contextual e mascaramento/anônimização configurável (documento-04, Seções 3–4).
- Logs assinados, correlação intent_id/plan_id, e auditoria imutável em ledger.
- Políticas de rate limiting adaptativas, proteção contra payload oversize e validação de assinatura de imagens durante deploy.

## Observabilidade
- Métricas principais: `neural_hive_gateway_requests_total`, latência p95/p99, taxa de rejeição por política, eventos de fallback edge.
- Traces OTel com baggage `intent.id`, `channel`, `confidence`. Logs estruturados em Loki.
- Dashboards Grafana: visão multicanal, erro por domínio, gating de baixa confiança.

## Riscos e Ações
- **Sobrecarga de canal específico**: expandir instâncias edge e aplicar throttling dinâmico.
- **Drift de modelos de pré-processamento**: monitorar accuracy e executar re-treinamento via Fase 5 (documento-05, Seção 2.5).
- **Config drifts**: reforçar GitOps e políticas OPA para manifests do gateway.

## Próximos Passos Sugeridos
1. Implementar assinatura Sigstore no pipeline de build para imagens do gateway (ADR-0003, Fase 2).
2. Automatizar validação de ApiAsset via workflow CI, garantindo metadados obrigatórios (ADR-0010).
3. Expandir testes de caos focados em perda de conectividade edge e comportamento de failover.
