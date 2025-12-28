{{/*
Consensus Engine - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "consensus-engine.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "consensus-engine.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "consensus-engine.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "consensus-engine.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "consensus-engine" "layer" "cognitiva") }}
neural-hive.io/domain: consensus
{{- end }}

{{- define "consensus-engine.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "consensus-engine.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "consensus-engine.configMapName" -}}
{{- include "neural-hive.configMapName" . }}
{{- end }}

{{- define "consensus-engine.secretName" -}}
{{- printf "%s-secrets" (include "consensus-engine.fullname" .) }}
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "consensus-engine.context" -}}
fullname: {{ include "consensus-engine.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "consensus-engine.labels" . | indent 2 }}
selectorLabels:
{{ include "consensus-engine.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "consensus-engine.serviceAccountName" . }}
{{- end }}
