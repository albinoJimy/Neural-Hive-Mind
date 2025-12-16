{{/*
Expand the name of the chart.
*/}}
{{- define "queen-agent.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "queen-agent.fullname" -}}
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
{{- define "queen-agent.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "queen-agent.labels" -}}
helm.sh/chart: {{ include "queen-agent.chart" . }}
{{ include "queen-agent.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
neural-hive.io/layer: coordination
neural-hive.io/component: queen-agent
{{- end }}

{{/*
Selector labels
*/}}
{{- define "queen-agent.selectorLabels" -}}
app.kubernetes.io/name: {{ include "queen-agent.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app: {{ include "queen-agent.name" . }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "queen-agent.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "queen-agent.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
ConfigMap name helper
*/}}
{{- define "queen-agent.configMapName" -}}
{{ include "queen-agent.fullname" . }}-config
{{- end }}
