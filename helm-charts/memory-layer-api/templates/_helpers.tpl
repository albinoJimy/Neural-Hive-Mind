{{/*
Memory Layer API - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "memory-layer-api.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "memory-layer-api.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "memory-layer-api.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "memory-layer-api.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "memory-layer-api" "layer" "conhecimento-dados") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: memory-management
{{- end }}

{{- define "memory-layer-api.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "memory-layer-api.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "memory-layer-api.configMapName" -}}
{{ include "memory-layer-api.fullname" . }}-config
{{- end }}

{{- define "memory-layer-api.secretName" -}}
{{ include "memory-layer-api.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "memory-layer-api.context" -}}
fullname: {{ include "memory-layer-api.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "memory-layer-api.labels" . | indent 2 }}
selectorLabels:
{{ include "memory-layer-api.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "memory-layer-api.serviceAccountName" . }}
{{- end }}
