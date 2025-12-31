{{/*
Queen Agent - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "queen-agent.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "queen-agent.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "queen-agent.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "queen-agent.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "queen-agent" "layer" "coordination") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: hive-coordination
{{- end }}

{{- define "queen-agent.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "queen-agent.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "queen-agent.configMapName" -}}
{{ include "queen-agent.fullname" . }}-config
{{- end }}

{{- define "queen-agent.secretName" -}}
{{ include "queen-agent.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "queen-agent.context" -}}
fullname: {{ include "queen-agent.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "queen-agent.labels" . | indent 2 }}
selectorLabels:
{{ include "queen-agent.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "queen-agent.serviceAccountName" . }}
{{- end }}
