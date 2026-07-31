# syntax=docker/dockerfile:1.7

FROM node:22.14.0-alpine AS dependencies
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --ignore-scripts

FROM node:22.14.0-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=dependencies /app/node_modules ./node_modules
COPY apps/web ./
ARG BACKEND_API_ORIGIN=http://127.0.0.1:8000
ENV BACKEND_API_ORIGIN=$BACKEND_API_ORIGIN
RUN npm run build

FROM node:22.14.0-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup --system --gid 10001 oncoagent \
    && adduser --system --uid 10001 --ingroup oncoagent oncoagent
COPY --from=builder --chown=oncoagent:oncoagent /app/public ./public
COPY --from=builder --chown=oncoagent:oncoagent /app/.next/standalone ./
COPY --from=builder --chown=oncoagent:oncoagent /app/.next/static ./.next/static
USER oncoagent
EXPOSE 3000
CMD ["node", "server.js"]
