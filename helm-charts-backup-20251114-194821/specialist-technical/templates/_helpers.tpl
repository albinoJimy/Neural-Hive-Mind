{{/*
Expand the name of the chart.
*/}}
{{- define "specialist-technical.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "specialist-technical.fullname" -}}
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
{{- define "specialist-technical.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "specialist-technical.labels" -}}
helm.sh/chart: {{ include "specialist-technical.chart" . }}
{{ include "specialist-technical.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/component: technical-specialist
neural-hive.io/layer: cognitiva
neural-hive.io/domain: technical-analysis
{{- end }}

{{/*
Selector labels
*/}}
{{- define "specialist-technical.selectorLabels" -}}
app.kubernetes.io/name: {{ include "specialist-technical.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "specialist-technical.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "specialist-technical.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create ConfigMap name
*/}}
{{- define "specialist-technical.configMapName" -}}
{{ include "specialist-technical.fullname" . }}-config
{{- end }}

{{/*
Create Secret name
*/}}
{{- define "specialist-technical.secretName" -}}
{{ include "specialist-technical.fullname" . }}-secrets
{{- end }}
