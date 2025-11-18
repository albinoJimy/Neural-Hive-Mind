{{/*
Expand the name of the chart.
*/}}
{{- define "execution-ticket-service.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "execution-ticket-service.fullname" -}}
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
{{- define "execution-ticket-service.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "execution-ticket-service.labels" -}}
helm.sh/chart: {{ include "execution-ticket-service.chart" . }}
{{ include "execution-ticket-service.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: orchestration
neural-hive.io/layer: orchestration
{{- end }}

{{/*
Selector labels
*/}}
{{- define "execution-ticket-service.selectorLabels" -}}
app.kubernetes.io/name: {{ include "execution-ticket-service.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "execution-ticket-service.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "execution-ticket-service.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create the name of the ConfigMap to use
*/}}
{{- define "execution-ticket-service.configMapName" -}}
{{- printf "%s-config" (include "execution-ticket-service.fullname" .) }}
{{- end }}

{{/*
Create the name of the Secret to use
*/}}
{{- define "execution-ticket-service.secretName" -}}
{{- printf "%s-secrets" (include "execution-ticket-service.fullname" .) }}
{{- end }}
