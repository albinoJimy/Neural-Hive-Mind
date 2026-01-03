{{/*
Explainability API - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funcoes do template comum via dependencia
*/}}
{{- define "explainability-api.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "explainability-api.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "explainability-api.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "explainability-api.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "explainability-api" "layer" "transparencia") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: audit-transparency
{{- end }}

{{- define "explainability-api.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "explainability-api.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "explainability-api.configMapName" -}}
{{ include "explainability-api.fullname" . }}-config
{{- end }}

{{- define "explainability-api.secretName" -}}
{{ include "explainability-api.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "explainability-api.context" -}}
fullname: {{ include "explainability-api.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "explainability-api.labels" . | indent 2 }}
selectorLabels:
{{ include "explainability-api.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "explainability-api.serviceAccountName" . }}
{{- end }}
