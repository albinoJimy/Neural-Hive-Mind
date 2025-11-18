{{/*
Expand the name of the chart.
*/}}
{{- define "consensus-engine.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "consensus-engine.fullname" -}}
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
{{- define "consensus-engine.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "consensus-engine.labels" -}}
helm.sh/chart: {{ include "consensus-engine.chart" . }}
{{ include "consensus-engine.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: consensus-aggregator
neural-hive.io/layer: cognitiva
neural-hive.io/domain: consensus
{{- with .Values.labels }}
{{- toYaml . | nindent 0 }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "consensus-engine.selectorLabels" -}}
app.kubernetes.io/name: {{ include "consensus-engine.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "consensus-engine.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "consensus-engine.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create the name of the ConfigMap
*/}}
{{- define "consensus-engine.configMapName" -}}
{{- printf "%s-config" (include "consensus-engine.fullname" .) }}
{{- end }}

{{/*
Create the name of the Secret
*/}}
{{- define "consensus-engine.secretName" -}}
{{- printf "%s-secrets" (include "consensus-engine.fullname" .) }}
{{- end }}
