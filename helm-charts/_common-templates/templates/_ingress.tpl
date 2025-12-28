{{/*
Neural Hive Mind - Template Comum de Ingress
Uso: {{ include "neural-hive.ingress" (dict "values" .Values "context" $ctx) }}
*/}}
{{- define "neural-hive.ingress" -}}
{{- $values := .values }}
{{- $context := .context }}
{{- if $values.ingress.enabled }}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ $context.fullname }}
  namespace: {{ $context.namespace }}
  labels:
    {{- $context.labels | nindent 4 }}
  {{- with $values.ingress.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  {{- if $values.ingress.className }}
  ingressClassName: {{ $values.ingress.className }}
  {{- end }}
  {{- if $values.ingress.tls }}
  tls:
    {{- range $values.ingress.tls }}
    - hosts:
        {{- range .hosts }}
        - {{ . | quote }}
        {{- end }}
      secretName: {{ .secretName }}
    {{- end }}
  {{- end }}
  rules:
    {{- range $values.ingress.hosts }}
    - host: {{ .host | quote }}
      http:
        paths:
          {{- range .paths }}
          - path: {{ .path }}
            pathType: {{ .pathType }}
            backend:
              service:
                name: {{ $context.fullname }}
                port:
                  {{- if .servicePort }}
                  number: {{ .servicePort }}
                  {{- else }}
                  number: {{ $values.service.ports.http.port }}
                  {{- end }}
          {{- end }}
    {{- end }}
{{- end }}
{{- end -}}
