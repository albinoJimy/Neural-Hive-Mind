{{/*
Specialist Business - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "specialist-business.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "specialist-business.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "specialist-business.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "specialist-business.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "specialist-business" "layer" "cognitiva") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: business-analysis
{{- end }}

{{- define "specialist-business.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "specialist-business.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "specialist-business.configMapName" -}}
{{ include "specialist-business.fullname" . }}-config
{{- end }}

{{- define "specialist-business.secretName" -}}
{{ include "specialist-business.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "specialist-business.context" -}}
fullname: {{ include "specialist-business.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "specialist-business.labels" . | indent 2 }}
selectorLabels:
{{ include "specialist-business.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "specialist-business.serviceAccountName" . }}
{{- end }}
