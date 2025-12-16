# Checklist de Deployment do Fluxo B - Semantic Translation Engine e Specialists

Use este checklist para rastrear cada etapa do deployment manual do Fluxo B em ambientes Kubeadm. Leia o item correspondente no guia `docs/manual-deployment/06-fluxo-b-deployment-manual-guide.md` antes de marcar `[x]`. Adicione observações ao final, conforme necessário.

---

## Seção 1: Pré-requisitos

- [ ] Cluster Kubeadm acessível (`kubectl cluster-info`).
- [ ] 3 nós em `Ready` (1 master + 2 workers).
- [ ] Namespaces de infraestrutura existem (`kafka`, `neo4j-cluster`, `mongodb-cluster`, `redis-cluster`, `mlflow`, `observability`).
- [ ] Pods de infraestrutura `Running` (Kafka, Neo4j, MongoDB, Redis, MLflow).
- [ ] Fluxo A operacional (Gateway/comsumidores `intentions.*`).
- [ ] 6 imagens presentes no containerd (`semantic-translation-engine:1.0.0`, `specialist-*:1.0.0`).
- [ ] Ferramentas instaladas (`kubectl`, `helm`, `curl`, `jq`, `grpcurl`, `yq`).
- [ ] ≥5 GB livres em `/var/lib/containerd`.
- [ ] Recursos disponíveis ≥2.5 CPU / ≥6 GiB (`kubectl top nodes`).

## Seção 2: Preparação de Valores

- [ ] Arquivo `environments/local/fluxo-b-config.yaml` revisado.
- [ ] Script `10-prepare-fluxo-b-values.sh` executado com sucesso.
- [ ] Arquivos `values-local-generated.yaml` gerados para:
  - [ ] `helm-charts/semantic-translation-engine/values-local-generated.yaml`
  - [ ] `helm-charts/specialist-business/values-local-generated.yaml`
  - [ ] `helm-charts/specialist-technical/values-local-generated.yaml`
  - [ ] `helm-charts/specialist-behavior/values-local-generated.yaml`
  - [ ] `helm-charts/specialist-evolution/values-local-generated.yaml`
  - [ ] `helm-charts/specialist-architecture/values-local-generated.yaml`
- [ ] Valores validados (pullPolicy=Never, endpoints corretos, gRPC porta 50051).

## Seção 3: Criação de Namespace

- [ ] Namespace `semantic-translation` criado.
- [ ] Labels aplicadas (`neural-hive-mind.org/layer=cognitiva`, `neural-hive-mind.org/flow=fluxo-b`).
- [ ] `kubectl get namespace semantic-translation --show-labels` confirma labels.

## Seção 4: Deployment do Semantic Translation Engine

- [ ] Helm release `semantic-translation-engine` instalado com `--wait --timeout 10m`.
- [ ] `kubectl rollout status` concluído.
- [ ] Pod `semantic-translation-engine` em `Running`.
- [ ] Pod `Ready 1/1`.
- [ ] Logs mostram `Application startup complete`.
- [ ] Logs mostram `Kafka consumer initialized`.
- [ ] Logs mostram `Neo4j connection established`.
- [ ] Logs mostram `MongoDB connection established`.
- [ ] Service `semantic-translation-engine` criado (ClusterIP, porta 8000).
- [ ] ConfigMap `semantic-translation-engine-config` presente.
- [ ] Secret `semantic-translation-engine-secret` presente.

## Seção 5: Deployment dos Specialists

- [ ] `specialist-business` instalado (`Running/Ready`) com logs `gRPC server started`.
- [ ] `specialist-technical` instalado com logs `gRPC server started`.
- [ ] `specialist-behavior` instalado com logs `gRPC server started`.
- [ ] `specialist-evolution` instalado com logs `gRPC server started`.
- [ ] `specialist-architecture` instalado com logs `gRPC server started`.
- [ ] Total de 6 pods `Running` no namespace `semantic-translation`.

## Seção 6: Validação de Health e Readiness

- [ ] STE `/health` retorna `{"status":"healthy"}`.
- [ ] STE `/ready` retorna `{"status":"ready"}`.
- [ ] STE `/status` indica `kafka_consumer_ready`, `neo4j_connected`, `mongodb_connected`.
- [ ] Specialist-business `/health` e `/ready` retornam `healthy/ready`.
- [ ] Specialist-technical `/health` e `/ready` retornam `healthy/ready`.
- [ ] Specialist-behavior `/health` e `/ready` retornam `healthy/ready`.
- [ ] Specialist-evolution `/health` e `/ready` retornam `healthy/ready`.
- [ ] Specialist-architecture `/health` e `/ready` retornam `healthy/ready`.

## Seção 7: Teste de Consumo Kafka

- [ ] Consumer group `semantic-translation-engine-local` ativo (`--describe`).
- [ ] Lag do consumer group < 100 mensagens.
- [ ] Intenção de teste enviada via Gateway.
- [ ] Logs do STE mostram `Processing intent <intent_id>`.
- [ ] Logs do STE mostram `Enriching context from Neo4j`.
- [ ] Logs do STE mostram `Decomposing objective into tasks`.
- [ ] Logs do STE mostram `Evaluating plan with specialists`.
- [ ] Logs do STE mostram `Cognitive plan generated`.
- [ ] Logs do STE mostram `Plan published to plans.ready`.
- [ ] Tópico `plans.ready` possui mensagens (`kafka-console-consumer --max-messages 1`).
- [ ] Mensagem contém `plan_id`, `intent_id`, `tasks`, `risk_score`.

## Seção 8: Verificação de Comunicação gRPC

- [ ] `grpcurl` instalado.
- [ ] Specialist-business `grpc.health.v1/Check` retorna `SERVING`.
- [ ] Specialist-technical `grpc.health.v1/Check` retorna `SERVING`.
- [ ] Specialist-behavior `grpc.health.v1/Check` retorna `SERVING`.
- [ ] Specialist-evolution `grpc.health.v1/Check` retorna `SERVING`.
- [ ] Specialist-architecture `grpc.health.v1/Check` retorna `SERVING`.
- [ ] Logs dos specialists mostram `Received EvaluatePlan request`.
- [ ] Logs dos specialists mostram `Opinion generated with confidence`.

## Seção 9: Validação de Persistência MongoDB

- [ ] Login no MongoDB (`mongosh`) concluído.
- [ ] Collection `cognitive_ledger` existe.
- [ ] `cognitive_ledger` possui documentos (count > 0).
- [ ] Documento de exemplo exibido (`plan_id`, `intent_id`, `risk_score`).
- [ ] Collection `specialist_opinions` existe.
- [ ] `specialist_opinions` possui documentos (count > 0).
- [ ] Opiniões de cinco specialists presentes (`specialist_type` variado).
- [ ] Registros contêm `confidence_score`, `recommendation`, `reasoning_summary`.

## Seção 10: Validação de Consultas Neo4j

- [ ] Login no Neo4j (`cypher-shell`) concluído.
- [ ] `MATCH (n) RETURN count(n)` retorna `total_nodes > 0`.
- [ ] Query de exemplo (`MATCH (i:Intent)-[:ENRICHED_BY]->(c:Context)`) retorna dados.

## Seção 11: Observabilidade (Opcional)

- [ ] ServiceMonitors criados para STE e cinco specialists.
- [ ] Prometheus identifica 6 targets (`curl /api/v1/targets`).
- [ ] Endpoints `/metrics` acessíveis para STE e specialists.
- [ ] Dashboards Grafana para Fluxo B (se aplicável).
- [ ] Tracing Jaeger habilitado (opcional).

## Seção 12: Validação Automatizada

- [ ] Script `11-validate-fluxo-b-deployment.sh` executado.
- [ ] Relatório `/tmp/fluxo-b-validation-report.json` gerado.
- [ ] Resumo `X/Y` checks passou documentado.
- [ ] Falhas críticas resolvidas ou justificadas.
- [ ] Warnings revisados/documentados.

## Seção 13: Troubleshooting (se necessário)

- [ ] Pods em `CrashLoopBackOff` investigados (`kubectl logs`, `kubectl describe`).
- [ ] Problemas de conectividade resolvidos (`nc -zv`, `nslookup`).
- [ ] Recursos insuficientes ajustados (redução de requests/replicas).
- [ ] Erros de serialização Avro corrigidos.
- [ ] Falhas gRPC diagnosticadas (portas, firewall, `grpcurl`).

## Seção 14: Conclusão

- [ ] Fluxo B operacional (STE + 5 specialists).
- [ ] Intenções processadas e planos gerados.
- [ ] Opiniões persistidas em MongoDB.
- [ ] Planos publicados em `plans.ready` para o Fluxo C.
- [ ] Documentação de deployment atualizada (se necessário).
- [ ] Próximo passo planejado (Fluxo C - Consensus Engine).

---

### Notas Adicionais

- __Observações__: ________________________________________________
- __Datas/Timestamps__: ___________________________________________
- __Problemas encontrados__: ______________________________________
- __Ações corretivas__: ___________________________________________

---

> Este checklist deve ser utilizado lado a lado com o guia manual detalhado e os scripts `10-prepare-fluxo-b-values.sh` e `11-validate-fluxo-b-deployment.sh`.
