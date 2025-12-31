{{/*
Semantic Translation Engine - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "semantic-translation-engine.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "semantic-translation-engine.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "semantic-translation-engine.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "semantic-translation-engine.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "semantic-translation-engine" "layer" "cognitiva") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: plan-generation
{{- end }}

{{- define "semantic-translation-engine.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "semantic-translation-engine.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "semantic-translation-engine.configMapName" -}}
{{ include "semantic-translation-engine.fullname" . }}-config
{{- end }}

{{- define "semantic-translation-engine.secretName" -}}
{{ include "semantic-translation-engine.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "semantic-translation-engine.context" -}}
fullname: {{ include "semantic-translation-engine.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "semantic-translation-engine.labels" . | indent 2 }}
selectorLabels:
{{ include "semantic-translation-engine.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "semantic-translation-engine.serviceAccountName" . }}
{{- end }}
