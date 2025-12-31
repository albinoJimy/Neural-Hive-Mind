{{/*
Service Registry - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "service-registry.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "service-registry.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "service-registry.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "service-registry.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "service-registry" "layer" "infrastructure") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: service-discovery
{{- end }}

{{- define "service-registry.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "service-registry.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "service-registry.configMapName" -}}
{{ include "service-registry.fullname" . }}-config
{{- end }}

{{- define "service-registry.secretName" -}}
{{ include "service-registry.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "service-registry.context" -}}
fullname: {{ include "service-registry.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "service-registry.labels" . | indent 2 }}
selectorLabels:
{{ include "service-registry.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "service-registry.serviceAccountName" . }}
{{- end }}
