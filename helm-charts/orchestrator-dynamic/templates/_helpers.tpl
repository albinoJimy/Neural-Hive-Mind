{{/*
Expand the name of the chart.
*/}}
{{- define "orchestrator-dynamic.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "orchestrator-dynamic.fullname" -}}
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
{{- define "orchestrator-dynamic.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "orchestrator-dynamic.labels" -}}
helm.sh/chart: {{ include "orchestrator-dynamic.chart" . }}
{{ include "orchestrator-dynamic.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: {{ index .Values.podLabels "app.kubernetes.io/component" | default "orchestration" }}
neural-hive.io/layer: {{ index .Values.podLabels "neural-hive.io/layer" | default "orchestration" }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "orchestrator-dynamic.selectorLabels" -}}
app.kubernetes.io/name: {{ include "orchestrator-dynamic.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "orchestrator-dynamic.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "orchestrator-dynamic.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create ConfigMap name
*/}}
{{- define "orchestrator-dynamic.configMapName" -}}
{{ include "orchestrator-dynamic.fullname" . }}-config
{{- end }}

{{/*
Create Secret name
*/}}
{{- define "orchestrator-dynamic.secretName" -}}
{{ include "orchestrator-dynamic.fullname" . }}-secrets
{{- end }}
