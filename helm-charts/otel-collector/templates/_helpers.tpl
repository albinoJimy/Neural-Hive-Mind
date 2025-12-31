{{/*
OpenTelemetry Collector - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "neural-hive-otel-collector.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "neural-hive-otel-collector.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "neural-hive-otel-collector.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "neural-hive-otel-collector.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "telemetry-collector" "layer" "observabilidade") }}
app.kubernetes.io/part-of: neural-hive-mind
neural.hive/component: telemetry-collector
neural.hive/layer: observabilidade
{{- end }}

{{- define "neural-hive-otel-collector.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "neural-hive-otel-collector.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "neural-hive-otel-collector.context" -}}
fullname: {{ include "neural-hive-otel-collector.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "neural-hive-otel-collector.labels" . | indent 2 }}
selectorLabels:
{{ include "neural-hive-otel-collector.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "neural-hive-otel-collector.serviceAccountName" . }}
{{- end }}

{{/*
Neural Hive-Mind correlation headers - CUSTOMIZAÇÃO ESPECÍFICA DO OTEL-COLLECTOR
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
Neural Hive-Mind baggage keys - CUSTOMIZAÇÃO ESPECÍFICA DO OTEL-COLLECTOR
*/}}
{{- define "neural-hive-otel-collector.baggageKeys" -}}
neural.hive.intent.id: "X-Neural-Hive-Intent-ID"
neural.hive.plan.id: "X-Neural-Hive-Plan-ID"
neural.hive.domain: "X-Neural-Hive-Domain"
neural.hive.user.id: "X-Neural-Hive-User-ID"
{{- end }}

{{/*
Environment-specific sampling rate - CUSTOMIZAÇÃO ESPECÍFICA DO OTEL-COLLECTOR
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
Environment-specific log level - CUSTOMIZAÇÃO ESPECÍFICA DO OTEL-COLLECTOR
*/}}
{{- define "neural-hive-otel-collector.logLevel" -}}
{{- if eq .Values.global.environment "production" -}}
warn
{{- else -}}
info
{{- end }}
{{- end }}

{{/*
Memory limit calculation for memory_limiter - CUSTOMIZAÇÃO ESPECÍFICA DO OTEL-COLLECTOR
*/}}
{{- define "neural-hive-otel-collector.memoryLimit" -}}
{{- $memoryLimit := .Values.collector.resources.limits.memory | regexReplaceAll "Gi" "" | float64 -}}
{{- $memoryLimitMiB := mul $memoryLimit 1024 -}}
{{- $limitMiB := mul $memoryLimitMiB 0.8 | int -}}
{{- $spikeLimitMiB := mul $memoryLimitMiB 0.2 | int -}}
limit_mib: {{ $limitMiB }}
spike_limit_mib: {{ $spikeLimitMiB }}
{{- end }}
