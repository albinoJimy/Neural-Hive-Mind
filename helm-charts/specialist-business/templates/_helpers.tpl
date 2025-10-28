{{/*
Expand the name of the chart.
*/}}
{{- define "specialist-business.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "specialist-business.fullname" -}}
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
{{- define "specialist-business.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "specialist-business.labels" -}}
helm.sh/chart: {{ include "specialist-business.chart" . }}
{{ include "specialist-business.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/component: business-specialist
neural-hive.io/layer: cognitiva
neural-hive.io/domain: business-analysis
{{- end }}

{{/*
Selector labels
*/}}
{{- define "specialist-business.selectorLabels" -}}
app.kubernetes.io/name: {{ include "specialist-business.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "specialist-business.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "specialist-business.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create ConfigMap name
*/}}
{{- define "specialist-business.configMapName" -}}
{{ include "specialist-business.fullname" . }}-config
{{- end }}

{{/*
Create Secret name
*/}}
{{- define "specialist-business.secretName" -}}
{{ include "specialist-business.fullname" . }}-secrets
{{- end }}
