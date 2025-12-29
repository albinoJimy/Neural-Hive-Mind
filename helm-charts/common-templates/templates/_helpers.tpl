{{/*
Neural Hive Mind - Funções Helper Comuns
Uso: Incluir este arquivo via Chart.yaml dependencies ou copiar para charts individuais
*/}}

{{/*
Expande o nome do chart.
Uso: {{ include "neural-hive.name" . }}
*/}}
{{- define "neural-hive.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Cria um nome completo qualificado padrão.
Uso: {{ include "neural-hive.fullname" . }}
*/}}
{{- define "neural-hive.fullname" -}}
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
Cria nome e versão do chart para uso em labels.
Uso: {{ include "neural-hive.chart" . }}
*/}}
{{- define "neural-hive.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Labels comuns - inclui labels Kubernetes padrão + labels customizados do Neural Hive Mind
Uso: {{ include "neural-hive.labels" (dict "context" . "component" "gateway" "layer" "application") }}
*/}}
{{- define "neural-hive.labels" -}}
{{- $context := .context }}
{{- $component := .component }}
{{- $layer := .layer }}
helm.sh/chart: {{ include "neural-hive.chart" $context }}
{{ include "neural-hive.selectorLabels" $context }}
{{- if $context.Chart.AppVersion }}
app.kubernetes.io/version: {{ $context.Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ $context.Release.Service }}
{{- if $component }}
app.kubernetes.io/component: {{ $component }}
neural-hive.io/component: {{ $component }}
{{- end }}
{{- if $layer }}
neural-hive.io/layer: {{ $layer }}
{{- end }}
{{- with $context.Values.labels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Labels de seletor - labels mínimos para seleção de pods
Uso: {{ include "neural-hive.selectorLabels" . }}
*/}}
{{- define "neural-hive.selectorLabels" -}}
app.kubernetes.io/name: {{ include "neural-hive.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Cria o nome do service account a ser usado
Uso: {{ include "neural-hive.serviceAccountName" . }}
*/}}
{{- define "neural-hive.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "neural-hive.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Cria o nome do ConfigMap
Uso: {{ include "neural-hive.configMapName" . }}
*/}}
{{- define "neural-hive.configMapName" -}}
{{- printf "%s-config" (include "neural-hive.fullname" .) }}
{{- end }}

{{/*
Cria o nome do Secret
Uso: {{ include "neural-hive.secretName" . }}
*/}}
{{- define "neural-hive.secretName" -}}
{{- printf "%s-secret" (include "neural-hive.fullname" .) }}
{{- end }}

{{/*
Constrói objeto de contexto para uso em templates
Uso: {{ $ctx := include "neural-hive.context" . | fromYaml }}
*/}}
{{- define "neural-hive.context" -}}
fullname: {{ include "neural-hive.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "neural-hive.labels" (dict "context" . "component" .Values.component "layer" .Values.layer) | indent 2 }}
selectorLabels:
{{ include "neural-hive.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "neural-hive.serviceAccountName" . }}
{{- end }}
