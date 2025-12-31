{{/*
Worker Agents - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "worker-agents.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "worker-agents.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "worker-agents.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "worker-agents.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "worker-agents" "layer" "execution") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: task-execution
{{- end }}

{{- define "worker-agents.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "worker-agents.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "worker-agents.configMapName" -}}
{{ include "worker-agents.fullname" . }}-config
{{- end }}

{{- define "worker-agents.secretName" -}}
{{ include "worker-agents.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "worker-agents.context" -}}
fullname: {{ include "worker-agents.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "worker-agents.labels" . | indent 2 }}
selectorLabels:
{{ include "worker-agents.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "worker-agents.serviceAccountName" . }}
{{- end }}
