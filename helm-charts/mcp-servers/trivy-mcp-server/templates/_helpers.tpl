{{/*
Trivy MCP Server - Template helpers
*/}}

{{- define "trivy-mcp-server.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "trivy-mcp-server.fullname" -}}
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

{{- define "trivy-mcp-server.labels" -}}
helm.sh/chart: {{ include "trivy-mcp-server.chart" . }}
{{ include "trivy-mcp-server.selectorLabels" . }}
app.kubernetes.io/version: {{ .Values.image.tag | default .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: {{ .Values.component }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive-mind.org/layer: {{ .Values.layer }}
{{- end }}

{{- define "trivy-mcp-server.selectorLabels" -}}
app.kubernetes.io/name: {{ include "trivy-mcp-server.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "trivy-mcp-server.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "trivy-mcp-server.context" -}}
name: {{ include "trivy-mcp-server.name" . }}
fullname: {{ include "trivy-mcp-server.fullname" . }}
labels: {{ include "trivy-mcp-server.labels" . | nindent 2 }}
selectorLabels: {{ include "trivy-mcp-server.selectorLabels" . | nindent 2 }}
{{- end }}
