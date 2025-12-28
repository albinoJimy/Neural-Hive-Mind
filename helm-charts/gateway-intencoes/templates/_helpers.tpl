{{/*
Gateway Intenções - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "gateway-intencoes.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "gateway-intencoes.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "gateway-intencoes.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "gateway-intencoes.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "gateway-intencoes" "layer" "application") }}
{{- end }}

{{- define "gateway-intencoes.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "gateway-intencoes.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "gateway-intencoes.configMapName" -}}
{{- include "neural-hive.configMapName" . }}
{{- end }}

{{- define "gateway-intencoes.secretName" -}}
{{- include "neural-hive.secretName" . }}
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "gateway-intencoes.context" -}}
fullname: {{ include "gateway-intencoes.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "gateway-intencoes.labels" . | indent 2 }}
selectorLabels:
{{ include "gateway-intencoes.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "gateway-intencoes.serviceAccountName" . }}
{{- end }}
