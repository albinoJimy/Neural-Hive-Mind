{{/*
Unified Gateway - Helpers de templates
Definições standalone (sem dependência de subchart common-templates).
*/}}

{{/*
Nome canónico do chart.
*/}}
{{- define "unified-gateway.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Nome completo do release.
Trunca a 63 chars (limite DNS de Kubernetes).
*/}}
{{- define "unified-gateway.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Identificador do chart (nome+versão) para labels.
*/}}
{{- define "unified-gateway.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Labels comuns aplicadas em todos os recursos.
*/}}
{{- define "unified-gateway.labels" -}}
helm.sh/chart: {{ include "unified-gateway.chart" . }}
{{ include "unified-gateway.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: neural-hive-mind
app.kubernetes.io/component: {{ .Values.component | default "unified-gateway" }}
neuralhive/layer: {{ .Values.layer | default "experiencia" }}
neural-hive.io/domain: api-gateway
{{- end }}

{{/*
Selector labels (subset estável para selectors de Service/Deployment).
NÃO incluir labels que mudem entre releases (evita selector imutável quebrar).
*/}}
{{- define "unified-gateway.selectorLabels" -}}
app.kubernetes.io/name: {{ include "unified-gateway.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Pod labels (selectorLabels + label legacy `app` para conformidade Gatekeeper).
Usar apenas em template.metadata.labels do Deployment.
NÃO usar em spec.selector.matchLabels (selector é imutável).
*/}}
{{- define "unified-gateway.podLabels" -}}
{{ include "unified-gateway.selectorLabels" . }}
app: {{ include "unified-gateway.name" . }}
component: {{ .Values.component | default "unified-gateway" }}
{{- end }}

{{/*
Nome do ServiceAccount (cria um se serviceAccount.create=true).
*/}}
{{- define "unified-gateway.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "unified-gateway.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Nome do ConfigMap derivado.
*/}}
{{- define "unified-gateway.configMapName" -}}
{{ include "unified-gateway.fullname" . }}-config
{{- end }}

{{/*
Nome do Secret derivado.
*/}}
{{- define "unified-gateway.secretName" -}}
{{ include "unified-gateway.fullname" . }}-secrets
{{- end }}

{{/*
Tag da imagem a usar (image.tag, fallback para .Chart.AppVersion).
*/}}
{{- define "unified-gateway.imageTag" -}}
{{- default .Chart.AppVersion .Values.image.tag }}
{{- end }}
