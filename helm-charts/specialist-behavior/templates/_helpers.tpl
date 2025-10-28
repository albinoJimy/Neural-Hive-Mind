{{/*
Expand the name of the chart.
*/}}
{{- define "specialist-behavior.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "specialist-behavior.fullname" -}}
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
{{- define "specialist-behavior.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "specialist-behavior.labels" -}}
helm.sh/chart: {{ include "specialist-behavior.chart" . }}
{{ include "specialist-behavior.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/component: behavior-specialist
neural-hive.io/layer: cognitiva
neural-hive.io/domain: behavior-analysis
{{- end }}

{{/*
Selector labels
*/}}
{{- define "specialist-behavior.selectorLabels" -}}
app.kubernetes.io/name: {{ include "specialist-behavior.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "specialist-behavior.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "specialist-behavior.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create ConfigMap name
*/}}
{{- define "specialist-behavior.configMapName" -}}
{{ include "specialist-behavior.fullname" . }}-config
{{- end }}

{{/*
Create Secret name
*/}}
{{- define "specialist-behavior.secretName" -}}
{{ include "specialist-behavior.fullname" . }}-secrets
{{- end }}
