# Official Node image, verified Linux/amd64 digest; build context is source-only.
FROM node:22-bookworm-slim@sha256:9f0dde62d10e7ff7a310ecaebd66225f6b46c17e6cb778449a77b05d3541bea2 AS build
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /opt/ocean/frontend-v1
COPY frontend-v1/package.json frontend-v1/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
WORKDIR /opt/ocean/frontend-v1/hosting
COPY frontend-v1/hosting/package.json frontend-v1/hosting/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
WORKDIR /opt/ocean
COPY frontend-v1/ frontend-v1/
COPY frontend/lib/csv.ts frontend/lib/csv.ts
WORKDIR /opt/ocean/frontend-v1/hosting
RUN npm run build

FROM node:22-bookworm-slim@sha256:9f0dde62d10e7ff7a310ecaebd66225f6b46c17e6cb778449a77b05d3541bea2 AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=8080
WORKDIR /opt/ocean
COPY --from=build --chown=node:node /opt/ocean/frontend-v1/hosting/.next/standalone/ ./
COPY --chown=node:node source-manifest.json ./source-manifest.json
COPY --chown=0:0 --chmod=0444 forwarded-adapter.cjs /opt/ocean/serving-frontend-adapter.cjs
USER node
EXPOSE 8080
CMD ["node", "--require", "/opt/ocean/serving-frontend-adapter.cjs", "hosting/server.js"]
