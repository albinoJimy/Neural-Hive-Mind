# Neural Hive Mind - Templates Comuns

Biblioteca de templates Helm reutilizáveis para os charts do Neural Hive Mind.

## Estrutura de Arquivos

```
_common-templates/
├── Chart.yaml                    # Definição do chart (type: library)
├── values.yaml                   # Valores padrão compartilhados
├── README.md                     # Esta documentação
└── templates/
    ├── _helpers.tpl              # Funções helper (name, fullname, labels, etc.)
    ├── _deployment.tpl           # Template de Deployment
    ├── _service.tpl              # Template de Service
    ├── _configmap.tpl            # Template de ConfigMap
    ├── _ingress.tpl              # Template de Ingress
    └── _secret.tpl               # Template de Secret
```

## Como Declarar a Dependência

No `Chart.yaml` do seu chart, adicione:

```yaml
dependencies:
  - name: _common-templates
    version: "0.1.0"
    repository: "file://../_common-templates"
    alias: common
```

Depois execute:

```bash
cd helm-charts/seu-chart
helm dependency update
```

## Templates Disponíveis

### neural-hive.deployment

Template completo de Deployment com suporte a:
- Réplicas e autoscaling
- Estratégia de rolling update
- Probes (startup, liveness, readiness)
- Security contexts
- Volumes e volumeMounts
- Init containers
- Annotations para Prometheus e Istio
- Checksum de config/secret para rollout automático

**Uso:**

```yaml
{{- $ctx := include "meu-chart.context" . | fromYaml }}
{{- $checksumConfig := include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
{{- $checksumSecret := include (print $.Template.BasePath "/secret.yaml") . | sha256sum }}

{{- $config := dict "checksumConfig" $checksumConfig "checksumSecret" $checksumSecret "env" $envVars "envFrom" $envFrom }}

{{- include "neural-hive.deployment" (dict "values" .Values "context" $ctx "config" $config) }}
```

**Parâmetros de config:**
- `checksumConfig`: Hash do ConfigMap para trigger de rollout
- `checksumSecret`: Hash do Secret para trigger de rollout
- `env`: Lista de variáveis de ambiente (formato Kubernetes)
- `envFrom`: Lista de envFrom (configMapRef, secretRef)

### neural-hive.service

Template de Service com suporte a:
- Tipos ClusterIP, NodePort, LoadBalancer
- Múltiplas portas configuráveis
- Annotations customizadas
- Labels para Prometheus

**Uso:**

```yaml
{{- $ctx := include "meu-chart.context" . | fromYaml }}
{{- include "neural-hive.service" (dict "values" .Values "context" $ctx) }}
```

**Estrutura esperada em values.yaml:**

```yaml
service:
  type: ClusterIP
  annotations: {}
  ports:
    http:
      port: 8000
      targetPort: 8000
      protocol: TCP
    metrics:
      port: 8080
      targetPort: 8080
      protocol: TCP
```

### neural-hive.configmap

Template de ConfigMap genérico.

**Uso:**

```yaml
{{- $ctx := include "meu-chart.context" . | fromYaml }}
{{- $data := dict "key1" "value1" "key2" "value2" }}
{{- include "neural-hive.configmap" (dict "values" .Values "context" $ctx "data" $data) }}
```

### neural-hive.ingress

Template de Ingress com suporte a TLS e múltiplos hosts.

**Uso:**

```yaml
{{- $ctx := include "meu-chart.context" . | fromYaml }}
{{- include "neural-hive.ingress" (dict "values" .Values "context" $ctx) }}
```

**Estrutura esperada em values.yaml:**

```yaml
ingress:
  enabled: true
  className: "istio"
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
  hosts:
    - host: app.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: app-tls
      hosts:
        - app.example.com
```

### neural-hive.secret

Template de Secret com encoding base64 automático.

**Uso:**

```yaml
{{- $ctx := include "meu-chart.context" . | fromYaml }}
{{- $data := dict "password" "mysecret" "api-key" "myapikey" }}
{{- include "neural-hive.secret" (dict "values" .Values "context" $ctx "data" $data) }}
```

## Funções Helper Disponíveis

| Função | Descrição |
|--------|-----------|
| `neural-hive.name` | Nome do chart |
| `neural-hive.fullname` | Nome completo com release |
| `neural-hive.chart` | Nome e versão do chart |
| `neural-hive.labels` | Labels padrão Kubernetes + Neural Hive |
| `neural-hive.selectorLabels` | Labels para seletores de pod |
| `neural-hive.serviceAccountName` | Nome do ServiceAccount |
| `neural-hive.configMapName` | Nome padrão do ConfigMap |
| `neural-hive.secretName` | Nome padrão do Secret |

## Aplicando values-defaults.yaml

O arquivo `values.yaml` da biblioteca contém valores padrão que podem ser herdados. Para sobrescrever, defina os mesmos campos no `values.yaml` do seu chart.

**Valores padrão importantes:**

```yaml
# Réplicas
replicaCount: 2

# Autoscaling
autoscaling:
  enabled: false
  minReplicas: 2
  maxReplicas: 10

# Resources padrão
resources:
  requests:
    cpu: 300m
    memory: 512Mi
  limits:
    cpu: 1000m
    memory: 1Gi

# Probes padrão
startupProbe:
  httpGet:
    path: /health
    port: 8000
  failureThreshold: 15

livenessProbe:
  httpGet:
    path: /health
    port: 8000
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  periodSeconds: 10

# Security contexts
podSecurityContext:
  runAsNonRoot: true
  runAsUser: 1000
  fsGroup: 1000

securityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
```

## Passos de Migração

1. **Adicionar dependência no Chart.yaml:**
   ```yaml
   dependencies:
     - name: _common-templates
       version: "0.1.0"
       repository: "file://../_common-templates"
       alias: common
   ```

2. **Atualizar _helpers.tpl** para usar funções comuns:
   ```yaml
   {{- define "meu-chart.name" -}}
   {{- include "neural-hive.name" . }}
   {{- end }}

   {{- define "meu-chart.context" -}}
   fullname: {{ include "meu-chart.fullname" . }}
   chartName: {{ .Chart.Name }}
   namespace: {{ .Release.Namespace }}
   appVersion: {{ .Chart.AppVersion }}
   labels:
   {{ include "meu-chart.labels" . | indent 2 }}
   selectorLabels:
   {{ include "meu-chart.selectorLabels" . | indent 2 }}
   serviceAccountName: {{ include "meu-chart.serviceAccountName" . }}
   {{- end }}
   ```

3. **Atualizar values.yaml** com estrutura esperada:
   ```yaml
   component: "meu-componente"
   layer: "application"

   service:
     type: ClusterIP
     ports:
       http:
         port: 8000
         targetPort: 8000
         protocol: TCP
   ```

4. **Substituir deployment.yaml e service.yaml** por chamadas aos templates comuns

5. **Executar helm dependency update:**
   ```bash
   helm dependency update
   ```

## Troubleshooting

### Erro: "template not found: neural-hive.deployment"

- Verifique se a dependência está declarada corretamente no Chart.yaml
- Execute `helm dependency update` no diretório do chart
- Confirme que o arquivo `charts/_common-templates-0.1.0.tgz` foi criado

### Labels ou names incorretos

- Verifique se o contexto está sendo construído corretamente no `_helpers.tpl`
- O contexto deve incluir `fullname`, `chartName`, `namespace`, `appVersion`, `labels`, `selectorLabels`, `serviceAccountName`

### Probes falhando

- Os probes padrão usam porta 8000 e paths `/health` e `/ready`
- Sobrescreva no seu `values.yaml` se necessário:
  ```yaml
  livenessProbe:
    httpGet:
      path: /custom-health
      port: 8080
  ```

### Portas não expostas corretamente

- Verifique a estrutura `service.ports` no values.yaml
- Cada porta deve ter `port`, `targetPort`, e opcionalmente `protocol`
