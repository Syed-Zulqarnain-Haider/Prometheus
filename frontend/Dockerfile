# Prometheus dashboard — production Next.js 15 image (multi-stage, standalone output).
#
# The five NEXT_PUBLIC_* values below are PUBLIC by design (the Firebase web config +
# the API base URL). Next inlines them into the CLIENT bundle at BUILD time, so they
# must be present during `npm run build`. They are NOT secrets — never pass real server
# secrets here. Requires `output: "standalone"` in next.config.mjs.

# ── Builder ──────────────────────────────────────────────────────────────────
FROM node:20-slim AS builder
WORKDIR /app

# Install deps from the lockfile first (better layer caching).
COPY package.json package-lock.json ./
RUN npm ci

# App source.
COPY . .

# Public build-time config, inlined into the client bundle (NOT secrets).
ARG NEXT_PUBLIC_FIREBASE_API_KEY
ARG NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN
ARG NEXT_PUBLIC_FIREBASE_PROJECT_ID
ARG NEXT_PUBLIC_FIREBASE_APP_ID
ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_FIREBASE_API_KEY=$NEXT_PUBLIC_FIREBASE_API_KEY \
    NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=$NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN \
    NEXT_PUBLIC_FIREBASE_PROJECT_ID=$NEXT_PUBLIC_FIREBASE_PROJECT_ID \
    NEXT_PUBLIC_FIREBASE_APP_ID=$NEXT_PUBLIC_FIREBASE_APP_ID \
    NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# ── Runner ───────────────────────────────────────────────────────────────────
FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000 \
    NEXT_TELEMETRY_DISABLED=1

# Copy the self-contained standalone server + static assets + public/, owned by the
# built-in non-root `node` user (uid 1000). server.js lives at the standalone root.
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public

USER node
EXPOSE 3000
CMD ["node", "server.js"]
