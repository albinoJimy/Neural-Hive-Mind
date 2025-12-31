{{/*
Specialist Architecture - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "specialist-architecture.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "specialist-architecture.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "specialist-architecture.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "specialist-architecture.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "specialist-architecture" "layer" "cognitiva") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: architecture-analysis
{{- end }}

{{- define "specialist-architecture.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "specialist-architecture.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "specialist-architecture.configMapName" -}}
{{ include "specialist-architecture.fullname" . }}-config
{{- end }}

{{- define "specialist-architecture.secretName" -}}
{{ include "specialist-architecture.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "specialist-architecture.context" -}}
fullname: {{ include "specialist-architecture.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "specialist-architecture.labels" . | indent 2 }}
selectorLabels:
{{ include "specialist-architecture.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "specialist-architecture.serviceAccountName" . }}
{{- end }}
