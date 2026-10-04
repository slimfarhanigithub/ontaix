# Build context is the repository root (pnpm workspace); the compose file sets it.
FROM node:22-alpine AS build
WORKDIR /workspace
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/studio/package.json apps/studio/
RUN pnpm install --frozen-lockfile --filter studio
COPY apps/studio apps/studio
# Where the built Studio calls the API. Empty keeps the in-browser mock (the compose stack);
# a deployment behind a proxy or ingress that serves the API on the same origin passes /api/v1.
ARG VITE_ONTAIX_API_URL=""
ENV VITE_ONTAIX_API_URL=$VITE_ONTAIX_API_URL
RUN pnpm --filter studio build

# The unprivileged nginx image runs as uid 101 and listens on 8080.
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
COPY apps/studio/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/apps/studio/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1
