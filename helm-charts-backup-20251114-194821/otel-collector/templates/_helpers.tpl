{{/*
Expand the name of the chart.
*/}}
{{- define "neural-hive-otel-collector.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "neural-hive-otel-collector.fullname" -}}
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
{{- define "neural-hive-otel-collector.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "neural-hive-otel-collector.labels" -}}
helm.sh/chart: {{ include "neural-hive-otel-collector.chart" . }}
{{ include "neural-hive-otel-collector.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/component: telemetry-collector
app.kubernetes.io/part-of: neural-hive-mind
neural.hive/component: telemetry-collector
neural.hive/layer: observabilidade
{{- end }}

{{/*
Selector labels
*/}}
{{- define "neural-hive-otel-collector.selectorLabels" -}}
app.kubernetes.io/name: {{ include "neural-hive-otel-collector.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "neural-hive-otel-collector.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "neural-hive-otel-collector.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Neural Hive-Mind correlation headers
*/}}
{{- define "neural-hive-otel-collector.correlationHeaders" -}}
- name: X-Neural-Hive-Intent-ID
  value: neural.hive.intent.id
- name: X-Neural-Hive-Plan-ID
  value: neural.hive.plan.id
- name: X-Neural-Hive-Domain
  value: neural.hive.domain
- name: X-Neural-Hive-User-ID
  value: neural.hive.user.id
{{- end }}

{{/*
Neural Hive-Mind baggage keys
*/}}
{{- define "neural-hive-otel-collector.baggageKeys" -}}
neural.hive.intent.id: "X-Neural-Hive-Intent-ID"
neural.hive.plan.id: "X-Neural-Hive-Plan-ID"
neural.hive.domain: "X-Neural-Hive-Domain"
neural.hive.user.id: "X-Neural-Hive-User-ID"
{{- end }}

{{/*
Environment-specific sampling rate
*/}}
{{- define "neural-hive-otel-collector.samplingRate" -}}
{{- if eq .Values.global.environment "production" -}}
5
{{- else if eq .Values.global.environment "staging" -}}
25
{{- else -}}
100
{{- end }}
{{- end }}

{{/*
Environment-specific log level
*/}}
{{- define "neural-hive-otel-collector.logLevel" -}}
{{- if eq .Values.global.environment "production" -}}
warn
{{- else -}}
info
{{- end }}
{{- end }}

{{/*
Memory limit calculation for memory_limiter
*/}}
{{- define "neural-hive-otel-collector.memoryLimit" -}}
{{- $memoryLimit := .Values.collector.resources.limits.memory | regexReplaceAll "Gi" "" | float64 -}}
{{- $memoryLimitMiB := mul $memoryLimit 1024 -}}
{{- $limitMiB := mul $memoryLimitMiB 0.8 | int -}}
{{- $spikeLimitMiB := mul $memoryLimitMiB 0.2 | int -}}
limit_mib: {{ $limitMiB }}
spike_limit_mib: {{ $spikeLimitMiB }}
{{- end }}