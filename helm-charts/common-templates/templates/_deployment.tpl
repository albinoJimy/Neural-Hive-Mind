{{/*
Neural Hive Mind - Common Deployment Template
Usage: {{ include "neural-hive.deployment" (dict "values" .Values "context" $ctx "config" $config) }}
*/}}
{{- define "neural-hive.deployment" -}}
{{- $values := .values }}
{{- $context := .context }}
{{- $config := .config }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ $context.fullname }}
  namespace: {{ $context.namespace }}
  labels:
    {{- if kindIs "string" $context.labels }}
    {{- $context.labels | nindent 4 }}
    {{- else }}
    {{- toYaml $context.labels | nindent 4 }}
    {{- end }}
spec:
  {{- if not $values.autoscaling.enabled }}
  replicas: {{ $values.replicaCount }}
  {{- end }}
  selector:
    matchLabels:
      {{- if kindIs "string" $context.selectorLabels }}
      {{- $context.selectorLabels | nindent 6 }}
      {{- else }}
      {{- toYaml $context.selectorLabels | nindent 6 }}
      {{- end }}
  strategy:
    type: {{ $values.deployment.strategy.type | default "RollingUpdate" }}
    {{- if eq ($values.deployment.strategy.type | default "RollingUpdate") "RollingUpdate" }}
    rollingUpdate:
      maxSurge: {{ $values.deployment.strategy.rollingUpdate.maxSurge | default 1 }}
      maxUnavailable: {{ $values.deployment.strategy.rollingUpdate.maxUnavailable | default 0 }}
    {{- end }}
  template:
    metadata:
      annotations:
        {{- if $config.checksumConfig }}
        checksum/config: {{ $config.checksumConfig }}
        {{- end }}
        {{- if $config.checksumSecret }}
        checksum/secret: {{ $config.checksumSecret }}
        {{- end }}
        {{- if $values.istio.enabled }}
        sidecar.istio.io/inject: "true"
        {{- end }}
        {{- if $values.observability.prometheus.enabled }}
        prometheus.io/scrape: "true"
        prometheus.io/port: {{ $values.service.ports.metrics.port | default "8080" | quote }}
        prometheus.io/path: "/metrics"
        {{- end }}
        {{- with $values.podAnnotations }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
      labels:
        {{- if kindIs "string" $context.selectorLabels }}
        {{- $context.selectorLabels | nindent 8 }}
        {{- else }}
        {{- toYaml $context.selectorLabels | nindent 8 }}
        {{- end }}
        {{- with $values.podLabels }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
    spec:
      {{- with $values.imagePullSecrets }}
      imagePullSecrets:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      serviceAccountName: {{ $context.serviceAccountName }}
      {{- if hasKey $values "enableServiceLinks" }}
      enableServiceLinks: {{ $values.enableServiceLinks }}
      {{- end }}
      {{- with $values.podSecurityContext }}
      securityContext:
        {{- toYaml . | nindent 8 }}
      {{- end }}

      {{- if $values.initContainers }}
      initContainers:
        {{- toYaml $values.initContainers | nindent 8 }}
      {{- end }}

      containers:
        - name: {{ $context.chartName }}
          image: "{{ $values.image.repository }}:{{ $values.image.tag | default $context.appVersion }}"
          imagePullPolicy: {{ $values.image.pullPolicy }}
          {{- with $config.command }}
          command:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          {{- with $config.args }}
          args:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          {{- with $values.securityContext }}
          securityContext:
            {{- toYaml . | nindent 12 }}
          {{- end }}

          ports:
          {{- range $name, $port := $values.service.ports }}
            - name: {{ $name }}
              containerPort: {{ $port.targetPort | default $port.port }}
              protocol: {{ $port.protocol | default "TCP" }}
          {{- end }}

          {{- if $values.startupProbe }}
          startupProbe:
            {{- toYaml $values.startupProbe | nindent 12 }}
          {{- end }}

          {{- if $values.livenessProbe }}
          livenessProbe:
            {{- toYaml $values.livenessProbe | nindent 12 }}
          {{- end }}

          {{- if $values.readinessProbe }}
          readinessProbe:
            {{- toYaml $values.readinessProbe | nindent 12 }}
          {{- end }}

          {{- with $values.resources }}
          resources:
            {{- toYaml . | nindent 12 }}
          {{- end }}

          {{- if or $config.env $config.envFrom }}
          {{- with $config.envFrom }}
          envFrom:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          {{- with $config.env }}
          env:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          {{- end }}

          {{- with $values.volumeMounts }}
          volumeMounts:
            {{- toYaml . | nindent 12 }}
          {{- end }}

      {{- with $values.volumes }}
      volumes:
        {{- toYaml . | nindent 8 }}
      {{- end }}

      {{- with $values.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}

      {{- with $values.affinity }}
      affinity:
        {{- toYaml . | nindent 8 }}
      {{- end }}

      {{- with $values.tolerations }}
      tolerations:
        {{- toYaml . | nindent 8 }}
      {{- end }}

      {{- with $values.topologySpreadConstraints }}
      topologySpreadConstraints:
        {{- toYaml . | nindent 8 }}
      {{- end }}
{{- end -}}
