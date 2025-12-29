{{/*
Neural Hive Mind - Template Comum de Secret
Uso: {{ include "neural-hive.secret" (dict "values" .Values "context" $ctx "data" $data) }}
*/}}
{{- define "neural-hive.secret" -}}
{{- $values := .values }}
{{- $context := .context }}
{{- $data := .data }}
{{- if $values.secrets.create }}
apiVersion: v1
kind: Secret
metadata:
  name: {{ $context.fullname }}-secret
  namespace: {{ $context.namespace }}
  labels:
    {{- $context.labels | nindent 4 }}
type: Opaque
data:
  {{- range $key, $value := $data }}
  {{ $key }}: {{ $value | b64enc | quote }}
  {{- end }}
{{- end }}
{{- end -}}
