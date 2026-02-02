{{/*
Approval Service - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funcoes do template comum via dependencia
*/}}
{{- define "approval-service.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "approval-service.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "approval-service.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "approval-service.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "approval-service" "layer" "orquestracao") }}
neural-hive.io/domain: approval
{{- end }}

{{- define "approval-service.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "approval-service.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "approval-service.configMapName" -}}
{{- include "neural-hive.configMapName" . }}
{{- end }}

{{- define "approval-service.secretName" -}}
{{- printf "%s-secrets" (include "approval-service.fullname" .) }}
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "approval-service.context" -}}
fullname: {{ include "approval-service.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "approval-service.labels" . | indent 2 }}
selectorLabels:
{{ include "approval-service.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "approval-service.serviceAccountName" . }}
{{- end }}
