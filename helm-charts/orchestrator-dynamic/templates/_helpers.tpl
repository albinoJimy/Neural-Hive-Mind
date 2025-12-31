{{/*
Orchestrator Dynamic - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "orchestrator-dynamic.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "orchestrator-dynamic.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "orchestrator-dynamic.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "orchestrator-dynamic.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "orchestrator-dynamic" "layer" "orchestration") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: workflow-orchestration
{{- end }}

{{- define "orchestrator-dynamic.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "orchestrator-dynamic.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "orchestrator-dynamic.configMapName" -}}
{{ include "orchestrator-dynamic.fullname" . }}-config
{{- end }}

{{- define "orchestrator-dynamic.secretName" -}}
{{ include "orchestrator-dynamic.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "orchestrator-dynamic.context" -}}
fullname: {{ include "orchestrator-dynamic.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "orchestrator-dynamic.labels" . | indent 2 }}
selectorLabels:
{{ include "orchestrator-dynamic.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "orchestrator-dynamic.serviceAccountName" . }}
{{- end }}
