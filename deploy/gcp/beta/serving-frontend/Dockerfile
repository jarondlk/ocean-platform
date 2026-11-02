# Exact accepted frontend artifact; no application rebuild or credential inputs.
FROM asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/frontend@sha256:adb5bc75dbc56d146bdf6e63f83a3dc8b3867b0318de0c2c02ba6fc56023e9dc
USER 0:0
COPY forwarded-adapter.cjs /opt/ocean/serving-frontend-adapter.cjs
COPY serving-frontend-manifest.json /opt/ocean/serving-frontend-manifest.json
RUN chmod 0444 /opt/ocean/serving-frontend-adapter.cjs /opt/ocean/serving-frontend-manifest.json
USER node
CMD ["node", "--require", "/opt/ocean/serving-frontend-adapter.cjs", "hosting/server.js"]
