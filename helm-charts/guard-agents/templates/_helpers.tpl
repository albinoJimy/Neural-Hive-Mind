{{/*
Guard Agents - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "guard-agents.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "guard-agents.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "guard-agents.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "guard-agents.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "guard-agents" "layer" "resilience") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: security-validation
{{- end }}

{{- define "guard-agents.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "guard-agents.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "guard-agents.configMapName" -}}
{{ include "guard-agents.fullname" . }}-config
{{- end }}

{{- define "guard-agents.secretName" -}}
{{ include "guard-agents.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "guard-agents.context" -}}
fullname: {{ include "guard-agents.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "guard-agents.labels" . | indent 2 }}
selectorLabels:
{{ include "guard-agents.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "guard-agents.serviceAccountName" . }}
{{- end }}
