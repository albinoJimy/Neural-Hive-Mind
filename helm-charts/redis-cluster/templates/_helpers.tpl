{{- define "redis-cluster.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "redis-cluster.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "redis-cluster.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "redis-cluster.labels" -}}
app.kubernetes.io/name: {{ include "redis-cluster.name" . }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "redis-cluster.selectorLabels" -}}
app.kubernetes.io/name: {{ include "redis-cluster.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "redis-cluster.serviceAccountName" -}}
{{- if .Values.rbac.create -}}
{{ include "redis-cluster.fullname" . }}-sa
{{- else -}}
{{ default "default" .Values.rbac.serviceAccountName }}
{{- end -}}
{{- end -}}

{{- define "redis-cluster.secretName" -}}
{{- if .Values.security.auth.existingSecret -}}
{{ .Values.security.auth.existingSecret }}
{{- else -}}
{{ include "redis-cluster.fullname" . }}-auth
{{- end -}}
{{- end -}}

{{- define "redis-cluster.tlsSecretName" -}}
{{- if .Values.security.tls.existingSecret -}}
{{ .Values.security.tls.existingSecret }}
{{- else -}}
{{ include "redis-cluster.fullname" . }}-tls
{{- end -}}
{{- end -}}
