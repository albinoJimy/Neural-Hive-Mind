{{/*
Expand the name of the chart.
*/}}
{{- define "specialist-architecture.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "specialist-architecture.fullname" -}}
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
{{- define "specialist-architecture.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "specialist-architecture.labels" -}}
helm.sh/chart: {{ include "specialist-architecture.chart" . }}
{{ include "specialist-architecture.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/component: architecture-specialist
neural-hive.io/layer: cognitiva
neural-hive.io/domain: architecture-analysis
{{- end }}

{{/*
Selector labels
*/}}
{{- define "specialist-architecture.selectorLabels" -}}
app.kubernetes.io/name: {{ include "specialist-architecture.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "specialist-architecture.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "specialist-architecture.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create ConfigMap name
*/}}
{{- define "specialist-architecture.configMapName" -}}
{{ include "specialist-architecture.fullname" . }}-config
{{- end }}

{{/*
Create Secret name
*/}}
{{- define "specialist-architecture.secretName" -}}
{{ include "specialist-architecture.fullname" . }}-secrets
{{- end }}
