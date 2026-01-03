{{/*
Optimizer Agents - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funcoes do template comum via dependencia
*/}}
{{- define "optimizer-agents.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "optimizer-agents.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "optimizer-agents.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "optimizer-agents.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "optimizer-agents" "layer" "otimizacao") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: continuous-improvement
{{- end }}

{{- define "optimizer-agents.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "optimizer-agents.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "optimizer-agents.configMapName" -}}
{{ include "optimizer-agents.fullname" . }}-config
{{- end }}

{{- define "optimizer-agents.secretName" -}}
{{ include "optimizer-agents.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "optimizer-agents.context" -}}
fullname: {{ include "optimizer-agents.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "optimizer-agents.labels" . | indent 2 }}
selectorLabels:
{{ include "optimizer-agents.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "optimizer-agents.serviceAccountName" . }}
{{- end }}
