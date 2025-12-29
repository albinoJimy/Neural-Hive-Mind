{{/*
Neural Hive Mind - Template Comum de ConfigMap
Uso: {{ include "neural-hive.configmap" (dict "values" .Values "context" $ctx "data" $data) }}
*/}}
{{- define "neural-hive.configmap" -}}
{{- $values := .values }}
{{- $context := .context }}
{{- $data := .data }}
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ $context.fullname }}-config
  namespace: {{ $context.namespace }}
  labels:
    {{- $context.labels | nindent 4 }}
data:
  {{- toYaml $data | nindent 2 }}
{{- end -}}
