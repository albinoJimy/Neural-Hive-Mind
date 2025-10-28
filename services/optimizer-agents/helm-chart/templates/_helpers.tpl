{{/*
Expand the name of the chart.
*/}}
{{- define "optimizer-agents.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "optimizer-agents.fullname" -}}
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
{{- define "optimizer-agents.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "optimizer-agents.labels" -}}
helm.sh/chart: {{ include "optimizer-agents.chart" . }}
{{ include "optimizer-agents.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "optimizer-agents.selectorLabels" -}}
app.kubernetes.io/name: {{ include "optimizer-agents.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app: optimizer-agents
component: optimizer
layer: estrategica
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "optimizer-agents.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "optimizer-agents.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
