{{/*
Expand the name of the chart.
*/}}
{{- define "optimizer-mcp-server.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "optimizer-mcp-server.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 59 | trimSuffix "-" -}}
{{- end -}}
{{- $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "optimizer-mcp-server.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "optimizer-mcp-server.selectorLabels" -}}
app.kubernetes.io/name: {{ include "optimizer-mcp-server.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "optimizer-mcp-server.labels" -}}
helm.sh/chart: {{ include "optimizer-mcp-server.chart" . }}
{{ include "optimizer-mcp-server.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{ end }}
{{- if .Values.podLabels }}
{{ toYaml .Values.podLabels }}
{{ end }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "optimizer-mcp-server.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "optimizer-mcp-server.name" .) -}}
{{- else -}}
{{- default "default" -}}
{{- end -}}
{{- end -}}
