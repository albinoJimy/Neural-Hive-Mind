{{/*
Code Forge - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "code-forge.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "code-forge.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "code-forge.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "code-forge.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "code-forge" "layer" "execution") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: code-generation
{{- end }}

{{- define "code-forge.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "code-forge.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "code-forge.configMapName" -}}
{{ include "code-forge.fullname" . }}-config
{{- end }}

{{- define "code-forge.secretName" -}}
{{ include "code-forge.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "code-forge.context" -}}
fullname: {{ include "code-forge.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "code-forge.labels" . | indent 2 }}
selectorLabels:
{{ include "code-forge.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "code-forge.serviceAccountName" . }}
{{- end }}
