{{/*
Expand the name of the chart.
*/}}
{{- define "self-healing-engine.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "self-healing-engine.fullname" -}}
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
{{- define "self-healing-engine.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "self-healing-engine.labels" -}}
helm.sh/chart: {{ include "self-healing-engine.chart" . }}
{{ include "self-healing-engine.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: self-healing
neural-hive.io/layer: resilience
neural-hive.io/domain: remediation
{{- with .Values.labels }}
{{- toYaml . | nindent 0 }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "self-healing-engine.selectorLabels" -}}
app.kubernetes.io/name: {{ include "self-healing-engine.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "self-healing-engine.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "self-healing-engine.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create the name of the ConfigMap
*/}}
{{- define "self-healing-engine.configMapName" -}}
{{- printf "%s-config" (include "self-healing-engine.fullname" .) }}
{{- end }}

{{/*
Create the name of the Secret
*/}}
{{- define "self-healing-engine.secretName" -}}
{{- printf "%s-secrets" (include "self-healing-engine.fullname" .) }}
{{- end }}
