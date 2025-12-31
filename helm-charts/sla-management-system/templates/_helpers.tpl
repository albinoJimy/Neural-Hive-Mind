{{/*
SLA Management System - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "sla-management-system.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "sla-management-system.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "sla-management-system.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "sla-management-system.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "sla-management-system" "layer" "monitoring") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: sla-management
{{- end }}

{{- define "sla-management-system.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "sla-management-system.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "sla-management-system.configMapName" -}}
{{ include "sla-management-system.fullname" . }}-config
{{- end }}

{{- define "sla-management-system.secretName" -}}
{{ include "sla-management-system.fullname" . }}-secrets
{{- end }}

{{/*
Operator ServiceAccount helper (específico deste chart)
*/}}
{{- define "sla-management-system.operatorServiceAccountName" -}}
{{- printf "%s-operator" (include "sla-management-system.fullname" .) }}
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "sla-management-system.context" -}}
fullname: {{ include "sla-management-system.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "sla-management-system.labels" . | indent 2 }}
selectorLabels:
{{ include "sla-management-system.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "sla-management-system.serviceAccountName" . }}
{{- end }}
