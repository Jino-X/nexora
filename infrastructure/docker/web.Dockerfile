# Nexora web app (Next.js standalone). Build from the repo root:
#   docker build -f infrastructure/docker/web.Dockerfile \
#     --build-arg NEXT_PUBLIC_API_URL=https://api.example.com -t nexora-web .
FROM node:24.22-alpine AS deps
RUN corepack enable
WORKDIR /repo
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY packages/shared-types/package.json packages/shared-types/
COPY packages/shared-config/package.json packages/shared-config/
RUN pnpm install --frozen-lockfile --filter @nexora/web...

FROM deps AS build
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_APP_URL
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
ARG NEXT_PUBLIC_LIVEKIT_URL
ENV NEXT_TELEMETRY_DISABLED=1 NEXT_OUTPUT=standalone
COPY packages ./packages
COPY apps/web ./apps/web
RUN pnpm --filter @nexora/web build

FROM node:24.22-alpine AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
RUN addgroup -S nexora && adduser -S nexora -G nexora
COPY --from=build --chown=nexora:nexora /repo/apps/web/.next/standalone ./
COPY --from=build --chown=nexora:nexora /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=nexora:nexora /repo/apps/web/public ./apps/web/public
USER nexora
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
