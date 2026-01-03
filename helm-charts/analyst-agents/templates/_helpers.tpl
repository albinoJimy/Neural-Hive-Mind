{{/*
Analyst Agents - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funcoes do template comum via dependencia
*/}}
{{- define "analyst-agents.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "analyst-agents.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "analyst-agents.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "analyst-agents.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "analyst-agents" "layer" "analise") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: insight-generation
{{- end }}

{{- define "analyst-agents.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "analyst-agents.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "analyst-agents.configMapName" -}}
{{ include "analyst-agents.fullname" . }}-config
{{- end }}

{{- define "analyst-agents.secretName" -}}
{{ include "analyst-agents.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "analyst-agents.context" -}}
fullname: {{ include "analyst-agents.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "analyst-agents.labels" . | indent 2 }}
selectorLabels:
{{ include "analyst-agents.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "analyst-agents.serviceAccountName" . }}
{{- end }}
