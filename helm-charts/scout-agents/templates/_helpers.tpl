{{/*
Scout Agents - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "scout-agents.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "scout-agents.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "scout-agents.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "scout-agents.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "scout-agents" "layer" "exploration") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: reconnaissance
{{- end }}

{{- define "scout-agents.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "scout-agents.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "scout-agents.configMapName" -}}
{{ include "scout-agents.fullname" . }}-config
{{- end }}

{{- define "scout-agents.secretName" -}}
{{ include "scout-agents.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "scout-agents.context" -}}
fullname: {{ include "scout-agents.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "scout-agents.labels" . | indent 2 }}
selectorLabels:
{{ include "scout-agents.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "scout-agents.serviceAccountName" . }}
{{- end }}
