{{/*
Release-scoped names and labels. With the release named "ontaix" the workloads are ontaix-api,
ontaix-gateway and ontaix-studio.
*/}}
{{- define "ontaix.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "ontaix.api.name" -}}
{{- printf "%s-api" (include "ontaix.fullname" .) -}}
{{- end -}}

{{- define "ontaix.gateway.name" -}}
{{- printf "%s-gateway" (include "ontaix.fullname" .) -}}
{{- end -}}

{{- define "ontaix.studio.name" -}}
{{- printf "%s-studio" (include "ontaix.fullname" .) -}}
{{- end -}}

{{- define "ontaix.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/* Selector labels of one component: pass (dict "root" . "component" "api"). */}}
{{- define "ontaix.selectorLabels" -}}
app.kubernetes.io/name: {{ .root.Chart.Name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/* Image reference of one component: pass (dict "root" . "image" .Values.api.image). */}}
{{- define "ontaix.image" -}}
{{- $tag := required "image.tag is required (the deploy workflow passes the commit SHA)" .root.Values.image.tag -}}
{{- if .root.Values.image.registry -}}
{{- printf "%s/%s:%s" .root.Values.image.registry .image.repository $tag -}}
{{- else -}}
{{- printf "%s:%s" .image.repository $tag -}}
{{- end -}}
{{- end -}}

{{/* Origins the API accepts sign-in and cookie-authenticated writes from, as a JSON list. */}}
{{- define "ontaix.allowedOrigins" -}}
{{- $origins := list -}}
{{- if and .Values.ingress.enabled .Values.ingress.host -}}
{{- $origins = append $origins (printf "https://%s" .Values.ingress.host) -}}
{{- end -}}
{{- range .Values.api.allowedOrigins -}}
{{- $origins = append $origins . -}}
{{- end -}}
{{- toJson $origins -}}
{{- end -}}

{{/* Speech custom subdomain, https and wss forms, when ONTAIX_SPEECH_ENDPOINT is set. */}}
{{- define "ontaix.speechOrigins" -}}
{{- $endpoint := index .Values.api.env "ONTAIX_SPEECH_ENDPOINT" | default "" | trimSuffix "/" -}}
{{- if $endpoint -}}
{{ $endpoint }} {{ replace "https://" "wss://" $endpoint }}
{{- end -}}
{{- end -}}

{{/* The Studio's Content Security Policy, one line. */}}
{{- define "ontaix.contentSecurityPolicy" -}}
{{- $connect := concat (list "'self'") .Values.studio.csp.connectSrc -}}
{{- $speech := include "ontaix.speechOrigins" . -}}
{{- if $speech -}}
{{- $connect = concat $connect (splitList " " $speech) -}}
{{- end -}}
{{- $style := concat (list "'self'" "'unsafe-inline'") .Values.studio.csp.styleSrc -}}
{{- $font := concat (list "'self'" "data:") .Values.studio.csp.fontSrc -}}
default-src 'self'; script-src 'self'; style-src {{ join " " $style }}; font-src {{ join " " $font }}; img-src 'self' data: blob:; connect-src {{ join " " $connect }}; worker-src 'self' blob:; media-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
{{- end -}}

{{/* Settings the chart computes or forbids must not arrive through api.env. */}}
{{- define "ontaix.validateApiEnv" -}}
{{- if hasKey .Values.api.env "ONTAIX_DEV_IDENTITY_HEADER" -}}
{{- fail "api.env.ONTAIX_DEV_IDENTITY_HEADER is never set in a cluster: it accepts an identity header without a credential" -}}
{{- end -}}
{{- if hasKey .Values.api.env "ONTAIX_DATABASE_URL" -}}
{{- fail "api.env.ONTAIX_DATABASE_URL is a secret: supply it through secrets.existingSecret or secrets.keyVault" -}}
{{- end -}}
{{- if hasKey .Values.api.env "ONTAIX_ALLOWED_ORIGINS" -}}
{{- fail "api.env.ONTAIX_ALLOWED_ORIGINS is computed from api.allowedOrigins and ingress.host" -}}
{{- end -}}
{{- if and (not .Values.secrets.existingSecret) (not .Values.secrets.keyVault.enabled) -}}
{{- fail "the API needs its secrets: set secrets.existingSecret or enable secrets.keyVault" -}}
{{- end -}}
{{- if and .Values.secrets.keyVault.enabled (not .Values.secrets.keyVault.name) -}}
{{- fail "secrets.keyVault.name is required when secrets.keyVault is enabled" -}}
{{- end -}}
{{- end -}}
