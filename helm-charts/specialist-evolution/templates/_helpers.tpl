{{/*
Expand the name of the chart.
*/}}
{{- define "specialist-evolution.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "specialist-evolution.fullname" -}}
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
{{- define "specialist-evolution.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "specialist-evolution.labels" -}}
helm.sh/chart: {{ include "specialist-evolution.chart" . }}
{{ include "specialist-evolution.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/component: evolution-specialist
neural-hive.io/layer: cognitiva
neural-hive.io/domain: evolution-analysis
{{- end }}

{{/*
Selector labels
*/}}
{{- define "specialist-evolution.selectorLabels" -}}
app.kubernetes.io/name: {{ include "specialist-evolution.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "specialist-evolution.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "specialist-evolution.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create ConfigMap name
*/}}
{{- define "specialist-evolution.configMapName" -}}
{{ include "specialist-evolution.fullname" . }}-config
{{- end }}

{{/*
Create Secret name
*/}}
{{- define "specialist-evolution.secretName" -}}
{{ include "specialist-evolution.fullname" . }}-secrets
{{- end }}
