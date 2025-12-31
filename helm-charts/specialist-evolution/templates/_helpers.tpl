{{/*
Specialist Evolution - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "specialist-evolution.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "specialist-evolution.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "specialist-evolution.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "specialist-evolution.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "specialist-evolution" "layer" "cognitiva") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: evolution-analysis
{{- end }}

{{- define "specialist-evolution.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "specialist-evolution.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "specialist-evolution.configMapName" -}}
{{ include "specialist-evolution.fullname" . }}-config
{{- end }}

{{- define "specialist-evolution.secretName" -}}
{{ include "specialist-evolution.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "specialist-evolution.context" -}}
fullname: {{ include "specialist-evolution.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "specialist-evolution.labels" . | indent 2 }}
selectorLabels:
{{ include "specialist-evolution.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "specialist-evolution.serviceAccountName" . }}
{{- end }}
