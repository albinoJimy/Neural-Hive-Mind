{{/*
Expand the name of the chart.
*/}}
{{- define "pii-service.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (DNS-1123 subdomain).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "pii-service.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "pii-service.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "pii-service.labels" -}}
helm.sh/chart: {{ include "pii-service.chart" . }}
{{ include "pii-service.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: neural-hive-mind
component: {{ .Values.component | default "pii-service" }}
neuralhive/layer: application
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "pii-service.selectorLabels" -}}
app.kubernetes.io/name: {{ include "pii-service.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Pod labels — selectorLabels + legacy `app` label (Gatekeeper requirement).
*/}}
{{- define "pii-service.podLabels" -}}
{{ include "pii-service.selectorLabels" . }}
app: {{ include "pii-service.name" . }}
component: {{ .Values.component | default "pii-service" }}
{{- with .Values.podLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Create the name of the service account to use.
*/}}
{{- define "pii-service.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "pii-service.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
ConfigMap name.
*/}}
{{- define "pii-service.configMapName" -}}
{{ include "pii-service.fullname" . }}-config
{{- end }}

{{/*
Secret name.
*/}}
{{- define "pii-service.secretName" -}}
{{ include "pii-service.fullname" . }}-secrets
{{- end }}
