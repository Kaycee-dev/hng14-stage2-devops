# syntax=docker/dockerfile:1.7
FROM node:20-bookworm-slim AS deps

ENV NODE_ENV=production \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    NPM_CONFIG_FUND=false

WORKDIR /build

COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund


FROM node:20-bookworm-slim AS runtime

ENV NODE_ENV=production \
    NPM_CONFIG_UPDATE_NOTIFIER=false

# hadolint ignore=DL3059
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid 10001 --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=deps /build/node_modules ./node_modules
COPY --chown=app:app package.json app.js healthcheck.js ./
COPY --chown=app:app views ./views

USER app

EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=4 \
    CMD node /app/healthcheck.js || exit 1

CMD ["node", "app.js"]
