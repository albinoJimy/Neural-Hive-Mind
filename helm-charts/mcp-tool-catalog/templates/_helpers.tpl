{{/*
MCP Tool Catalog - Helpers usando templates comuns do Neural Hive Mind
*/}}

{{/*
Usa funções do template comum via dependência
*/}}
{{- define "mcp-tool-catalog.name" -}}
{{- include "neural-hive.name" . }}
{{- end }}

{{- define "mcp-tool-catalog.fullname" -}}
{{- include "neural-hive.fullname" . }}
{{- end }}

{{- define "mcp-tool-catalog.chart" -}}
{{- include "neural-hive.chart" . }}
{{- end }}

{{- define "mcp-tool-catalog.labels" -}}
{{- include "neural-hive.labels" (dict "context" . "component" "mcp-tool-catalog" "layer" "infrastructure") }}
app.kubernetes.io/part-of: neural-hive-mind
neural-hive.io/domain: tool-management
{{- end }}

{{- define "mcp-tool-catalog.selectorLabels" -}}
{{- include "neural-hive.selectorLabels" . }}
{{- end }}

{{- define "mcp-tool-catalog.serviceAccountName" -}}
{{- include "neural-hive.serviceAccountName" . }}
{{- end }}

{{- define "mcp-tool-catalog.configMapName" -}}
{{ include "mcp-tool-catalog.fullname" . }}-config
{{- end }}

{{- define "mcp-tool-catalog.secretName" -}}
{{ include "mcp-tool-catalog.fullname" . }}-secrets
{{- end }}

{{/*
Contexto para uso nos templates comuns
*/}}
{{- define "mcp-tool-catalog.context" -}}
fullname: {{ include "mcp-tool-catalog.fullname" . }}
chartName: {{ .Chart.Name }}
namespace: {{ .Release.Namespace }}
appVersion: {{ .Chart.AppVersion }}
labels:
{{ include "mcp-tool-catalog.labels" . | indent 2 }}
selectorLabels:
{{ include "mcp-tool-catalog.selectorLabels" . | indent 2 }}
serviceAccountName: {{ include "mcp-tool-catalog.serviceAccountName" . }}
{{- end }}
