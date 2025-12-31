{{/*
Self Healing Engine - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "self-healing-engine.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "self-healing-engine.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "self-healing-engine.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "self-healing-engine.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "self-healing-engine" "layer" "resilience") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: remediation
{{- end }}

{{- define "self-healing-engine.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "self-healing-engine.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "self-healing-engine.configMapName" -}}
{{ include "self-healing-engine.fullname" . }}-config
{{- end }}

{{- define "self-healing-engine.secretName" -}}
{{ include "self-healing-engine.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "self-healing-engine.context" -}}
fullname: {{ include "self-healing-engine.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "self-healing-engine.labels" . | indent 2 }}
selectorLabels:
{{ include "self-healing-engine.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "self-healing-engine.serviceAccountName" . }}
{{- end }}
