{{/*
Expand the name of the chart.
*/}}
{{- define "nhm-neo4j.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "nhm-neo4j.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- printf "%s" $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "nhm-neo4j.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "nhm-neo4j.labels" -}}
helm.sh/chart: {{ include "nhm-neo4j.chart" . }}
{{ include "nhm-neo4j.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/layer: knowledge
neural-hive.io/component: semantic-graph
{{- end }}

{{/*
Selector labels
*/}}
{{- define "nhm-neo4j.selectorLabels" -}}
app.kubernetes.io/name: {{ include "nhm-neo4j.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "nhm-neo4j.serviceAccountName" -}}
{{- if .Values.rbac.create }}
{{- default (include "nhm-neo4j.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
