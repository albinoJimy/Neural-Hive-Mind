{{/*
Expand the name of the chart.
*/}}
{{- define "code-forge.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "code-forge.fullname" -}}
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
{{- define "code-forge.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "code-forge.labels" -}}
helm.sh/chart: {{ include "code-forge.chart" . }}
{{ include "code-forge.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: execution-layer
app.kubernetes.io/part-of: neural-hive-mind
{{- end }}

{{/*
Selector labels
*/}}
{{- define "code-forge.selectorLabels" -}}
app.kubernetes.io/name: {{ include "code-forge.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "code-forge.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "code-forge.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create the name of the ConfigMap
*/}}
{{- define "code-forge.configMapName" -}}
{{- printf "%s-config" (include "code-forge.fullname" .) }}
{{- end }}

{{/*
Create the name of the Secret
*/}}
{{- define "code-forge.secretName" -}}
{{- printf "%s-secrets" (include "code-forge.fullname" .) }}
{{- end }}
