{{/*
Specialist Behavior - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "specialist-behavior.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "specialist-behavior.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "specialist-behavior.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "specialist-behavior.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "specialist-behavior" "layer" "cognitiva") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: behavior-analysis
{{- end }}

{{- define "specialist-behavior.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "specialist-behavior.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "specialist-behavior.configMapName" -}}
{{ include "specialist-behavior.fullname" . }}-config
{{- end }}

{{- define "specialist-behavior.secretName" -}}
{{ include "specialist-behavior.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "specialist-behavior.context" -}}
fullname: {{ include "specialist-behavior.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "specialist-behavior.labels" . | indent 2 }}
selectorLabels:
{{ include "specialist-behavior.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "specialist-behavior.serviceAccountName" . }}
{{- end }}
