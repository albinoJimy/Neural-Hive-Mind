{{/*
Neural Hive Mind - Template Comum de Service
Uso: {{ include "neural-hive.service" (dict "values" .Values "context" $ctx) }}
*/}}
{{- define "neural-hive.service" -}}
{{- $values := .values }}
{{- $context := .context }}
apiVersion: v1
kind: Service
metadata:
  name: {{ $context.fullname }}
  namespace: {{ $context.namespace }}
  labels:
    {{- $context.labels | nindent 4 }}
    {{- if $values.observability.prometheus.enabled }}
    component: metrics
    neural.hive/metrics: "enabled"
    {{- end }}
  {{- with $values.service.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  type: {{ $values.service.type | default "ClusterIP" }}
  {{- if and (eq $values.service.type "LoadBalancer") $values.service.loadBalancerIP }}
  loadBalancerIP: {{ $values.service.loadBalancerIP }}
  {{- end }}
  {{- if and (eq $values.service.type "LoadBalancer") $values.service.loadBalancerSourceRanges }}
  loadBalancerSourceRanges:
    {{- toYaml $values.service.loadBalancerSourceRanges | nindent 4 }}
  {{- end }}
  ports:
  {{- range $name, $port := $values.service.ports }}
    - name: {{ $name }}
      port: {{ $port.port }}
      targetPort: {{ $port.targetPort | default $port.port }}
      protocol: {{ $port.protocol | default "TCP" }}
      {{- if and (eq $values.service.type "NodePort") $port.nodePort }}
      nodePort: {{ $port.nodePort }}
      {{- end }}
  {{- end }}
  selector:
    {{- $context.selectorLabels | nindent 4 }}
{{- end -}}
