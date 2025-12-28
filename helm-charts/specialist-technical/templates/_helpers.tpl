{{/*
Specialist Technical - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "specialist-technical.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "specialist-technical.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "specialist-technical.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "specialist-technical.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "specialist-technical" "layer" "cognitiva") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: technical-analysis
{{- end }}

{{- define "specialist-technical.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "specialist-technical.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "specialist-technical.configMapName" -}}
{{ include "specialist-technical.fullname" . }}-config
{{- end }}

{{- define "specialist-technical.secretName" -}}
{{ include "specialist-technical.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "specialist-technical.context" -}}
fullname: {{ include "specialist-technical.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "specialist-technical.labels" . | indent 2 }}
selectorLabels:
{{ include "specialist-technical.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "specialist-technical.serviceAccountName" . }}
{{- end }}
