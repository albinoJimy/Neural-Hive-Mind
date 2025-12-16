# Checklist de Deployment da Stack de Observabilidade - Neural Hive-Mind

Use esta checklist para acompanhar cada etapa descrita no guia `docs/manual-deployment/03-observability-manual-guide.md`. Marque `[x]` após concluir cada item e anote observações adicionais conforme necessário.

## 1. Pré-requisitos
- [ ] Cluster Kubeadm acessível e configurado
- [ ] Kubectl instalado e conectado ao cluster
- [ ] Helm 3.x instalado
- [ ] Repositórios Helm adicionados (prometheus-community, grafana, jaegertracing)
- [ ] StorageClass padrão configurado (local-path ou hostpath)
- [ ] Recursos mínimos verificados (≥4 vCPUs, ≥8 GiB RAM)
- [ ] Namespace `observability` criado

## 2. Preparação de Valores
- [ ] Arquivo `environments/local/observability-config.yaml` revisado
- [ ] Script `04-prepare-observability-values.sh` executado com sucesso
- [ ] Arquivos em `.tmp/observability-values/` verificados
  - [ ] `prometheus-values-local.yaml`
  - [ ] `grafana-values-local.yaml`
  - [ ] `jaeger-values-local.yaml`
- [ ] StorageClass detectado corretamente

## 3. Prometheus Stack
- [ ] Dependências do chart atualizadas (`helm dependency update`)
- [ ] Prometheus Stack instalado via Helm
- [ ] Prometheus Operator em Running
- [ ] Prometheus Server em Running e Ready
- [ ] AlertManager em Running
- [ ] Node Exporter DaemonSet ativo em todos os nós
- [ ] Kube State Metrics em Running
- [ ] PVCs do Prometheus e AlertManager em Bound
- [ ] CRDs instaladas (Prometheus, ServiceMonitor, AlertManager, PrometheusRule)
- [ ] Prometheus UI acessível via port-forward (porta 9090)
- [ ] Targets ativos verificados na UI
- [ ] Query `up{job="kubernetes-nodes"}` executada com sucesso

## 4. ServiceMonitors
- [ ] ServiceMonitors listados em todos os namespaces
- [ ] ≥5 ServiceMonitors com label `neural.hive/metrics: enabled`
- [ ] Prometheus descobrindo ServiceMonitors automaticamente (`/targets`)
- [ ] Métricas dos serviços Neural Hive coletadas

## 5. Grafana
- [ ] Dependências do chart atualizadas
- [ ] Grafana instalado via Helm
- [ ] Pod em Running e Ready
- [ ] PVC do Grafana em Bound
- [ ] Senha admin obtida do Secret
- [ ] UI acessível via port-forward (porta 3000)
- [ ] Login admin bem-sucedido
- [ ] Datasource Prometheus configurado e verde
- [ ] Datasource Jaeger configurado e verde
- [ ] Query de teste no Explore executada
- [ ] Dashboards padrão do Kubernetes importados (opcional)

## 6. Jaeger
- [ ] Dependências do chart atualizadas
- [ ] Jaeger instalado via Helm (modo all-in-one)
- [ ] Pod em Running e Ready
- [ ] Portas expostas (14250, 4317, 4318, 16686)
- [ ] UI acessível via port-forward (16686)
- [ ] OTLP gRPC endpoint acessível (4317)
- [ ] OTLP HTTP endpoint acessível (4318)
- [ ] ServiceMonitor do Jaeger criado
- [ ] Traces visíveis após deployment dos serviços

## 7. Validação Completa
- [ ] Script `05-validate-observability.sh` executado
- [ ] Todas as 25 validações aprovadas
- [ ] Relatório salvo em `.tmp/observability-validation-report.txt`
- [ ] Pods de todos os componentes em Running
- [ ] Serviços acessíveis
- [ ] PVCs em Bound
- [ ] Logs sem erros críticos
- [ ] Conectividade entre componentes validada

## 8. Integração e Testes
- [ ] Exemplars configurados no Prometheus
- [ ] Grafana navegando de métricas para traces
- [ ] Teste de envio de trace OTLP executado
- [ ] Métricas do Kubernetes visíveis no Prometheus
- [ ] Dashboards customizados do Neural Hive importados (opcional)

## 9. Documentação
- [ ] Credenciais de admin do Grafana armazenadas com segurança
- [ ] Endpoints dos serviços documentados
- [ ] Comandos de port-forward documentados
- [ ] Troubleshooting aplicado quando necessário

## 10. Próximos Passos
- [ ] Preparar deployment dos serviços Neural Hive (Gateway, STE, Specialists)
- [ ] Configurar dashboards customizados para fluxos A/B/C
- [ ] Configurar alertas customizados para SLOs
- [ ] Revisar guia `04-services-manual-guide.md`

---
Responsável: ______________________   Data: ____/____/____
Observações: ________________________________________________________________
