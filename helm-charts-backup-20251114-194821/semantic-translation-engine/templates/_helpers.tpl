{{/*
Expand the name of the chart.
*/}}
{{- define "semantic-translation-engine.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "semantic-translation-engine.fullname" -}}
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
{{- define "semantic-translation-engine.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "semantic-translation-engine.labels" -}}
helm.sh/chart: {{ include "semantic-translation-engine.chart" . }}
{{ include "semantic-translation-engine.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: semantic-translator
neural-hive.io/layer: cognitiva
neural-hive.io/domain: plan-generation
{{- with .Values.labels }}
{{- toYaml . | nindent 0 }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "semantic-translation-engine.selectorLabels" -}}
app.kubernetes.io/name: {{ include "semantic-translation-engine.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "semantic-translation-engine.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "semantic-translation-engine.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create the name of the ConfigMap
*/}}
{{- define "semantic-translation-engine.configMapName" -}}
{{- printf "%s-config" (include "semantic-translation-engine.fullname" .) }}
{{- end }}

{{/*
Create the name of the Secret
*/}}
{{- define "semantic-translation-engine.secretName" -}}
{{- printf "%s-secrets" (include "semantic-translation-engine.fullname" .) }}
{{- end }}
