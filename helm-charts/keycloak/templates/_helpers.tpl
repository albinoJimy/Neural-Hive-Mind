{{/*
Keycloak - Funções Helper
Delegam para templates comuns do neural-hive
*/}}

{{/*
Nome do chart
*/}}
{{- define "keycloak.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{/*
Nome completo qualificado
*/}}
{{- define "keycloak.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{/*
Nome e versão do chart
*/}}
{{- define "keycloak.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{/*
Labels padrão com component e layer específicos
*/}}
{{- define "keycloak.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "auth" "layer" "security") }}
{{- end }}

{{/*
Labels de seleção de pods
*/}}
{{- define "keycloak.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{/*
Nome da service account
*/}}
{{- define "keycloak.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{/*
Nome do ConfigMap
*/}}
{{- define "keycloak.configMapName" -}}
{{- include "neural-hive.configMapName" . }}
{{- end }}

{{/*
Nome do Secret
*/}}
{{- define "keycloak.secretName" -}}
{{- if .Values.auth.existingSecret }}
{{- .Values.auth.existingSecret }}
{{- else }}
{{- printf "%s-secret" (include "keycloak.fullname" .) }}
{{- end }}
{{- end }}

{{/*
Host do banco de dados
*/}}
{{- define "keycloak.databaseHost" -}}
{{- if .Values.postgresql.enabled }}
{{- printf "%s-postgresql" .Release.Name }}
{{- else }}
{{- .Values.externalDatabase.host }}
{{- end }}
{{- end }}

{{/*
Nome do secret do banco de dados
*/}}
{{- define "keycloak.databaseSecretName" -}}
{{- if .Values.postgresql.enabled }}
{{- printf "%s-postgresql" .Release.Name }}
{{- else if .Values.externalDatabase.existingSecret }}
{{- .Values.externalDatabase.existingSecret }}
{{- else }}
{{- printf "%s-db-secret" (include "keycloak.fullname" .) }}
{{- end }}
{{- end }}

{{/*
Chave do password no secret do banco de dados
*/}}
{{- define "keycloak.databaseSecretPasswordKey" -}}
{{- if .Values.postgresql.enabled }}
{{- "password" }}
{{- else if .Values.externalDatabase.existingSecretPasswordKey }}
{{- .Values.externalDatabase.existingSecretPasswordKey }}
{{- else }}
{{- "database-password" }}
{{- end }}
{{- end }}

{{/*
Nome do secret TLS
*/}}
{{- define "keycloak.tlsSecretName" -}}
{{- if .Values.tls.existingSecret }}
{{- .Values.tls.existingSecret }}
{{- else }}
{{- printf "%s-tls" (include "keycloak.fullname" .) }}
{{- end }}
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "keycloak.context" -}}
fullname: {{ include "keycloak.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "keycloak.labels" . | indent 2 }}
selectorLabels:
{{ include "keycloak.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "keycloak.serviceAccountName" . }}
{{- end }}
