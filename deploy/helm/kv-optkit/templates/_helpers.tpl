{{- define "kv-optkit.name" -}}
kv-optkit
{{- end -}}

{{- define "kv-optkit.fullname" -}}
{{ include "kv-optkit.name" . }}
{{- end -}}
