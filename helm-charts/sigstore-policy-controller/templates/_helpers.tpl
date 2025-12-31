{{/*
Sigstore Policy Controller - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "sigstore-policy-controller.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "sigstore-policy-controller.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "sigstore-policy-controller.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "sigstore-policy-controller.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "policy-controller" "layer" "security") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: image-verification
{{- end }}

{{- define "sigstore-policy-controller.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "sigstore-policy-controller.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "sigstore-policy-controller.context" -}}
fullname: {{ include "sigstore-policy-controller.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Values.webhook.namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "sigstore-policy-controller.labels" . | indent 2 }}
selectorLabels:
{{ include "sigstore-policy-controller.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "sigstore-policy-controller.serviceAccountName" . }}
{{- end }}
