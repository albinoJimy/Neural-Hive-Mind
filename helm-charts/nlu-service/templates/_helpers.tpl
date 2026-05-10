{{/*
NLU Service - Helpers padrão (chart standalone, sem dependência de common-templates).
*/}}

{{/*
Expand the name of the chart.
*/}}
{{- define "nlu-service.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "nlu-service.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "nlu-service.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "nlu-service.labels" -}}
helm.sh/chart: {{ include "nlu-service.chart" . }}
{{ include "nlu-service.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive-mind.org/component: {{ .Values.component | default "nlu-service" | quote }}
neural-hive-mind.org/layer: {{ .Values.layer | default "specialist" | quote }}
component: nlu
{{- end -}}

{{/*
Selector labels (must remain stable — Deployment selector é imutável).
*/}}
{{- define "nlu-service.selectorLabels" -}}
app.kubernetes.io/name: {{ include "nlu-service.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Pod labels (selectorLabels + label `app` legacy exigida pelo Gatekeeper).
Usar em template.metadata.labels do Pod, NÃO em selector.matchLabels.
Os valores em .Values.podLabels (se existirem) têm precedência — ex. permitem
overridar `app` numa instalação multi-tenant.
*/}}
{{- define "nlu-service.podLabels" -}}
{{- $base := dict "app" (include "nlu-service.name" .) "component" "nlu" -}}
{{- $merged := mergeOverwrite $base (.Values.podLabels | default dict) -}}
{{ include "nlu-service.selectorLabels" . }}
{{ toYaml $merged }}
{{- end -}}

{{/*
ConfigMap name
*/}}
{{- define "nlu-service.configMapName" -}}
{{ include "nlu-service.fullname" . }}-config
{{- end -}}
