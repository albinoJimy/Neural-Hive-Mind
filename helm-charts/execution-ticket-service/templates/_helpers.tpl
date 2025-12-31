{{/*
Execution Ticket Service - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "execution-ticket-service.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "execution-ticket-service.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "execution-ticket-service.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "execution-ticket-service.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "execution-ticket-service" "layer" "orchestration") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: ticket-management
{{- end }}

{{- define "execution-ticket-service.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "execution-ticket-service.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "execution-ticket-service.configMapName" -}}
{{ include "execution-ticket-service.fullname" . }}-config
{{- end }}

{{- define "execution-ticket-service.secretName" -}}
{{ include "execution-ticket-service.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "execution-ticket-service.context" -}}
fullname: {{ include "execution-ticket-service.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "execution-ticket-service.labels" . | indent 2 }}
selectorLabels:
{{ include "execution-ticket-service.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "execution-ticket-service.serviceAccountName" . }}
{{- end }}
