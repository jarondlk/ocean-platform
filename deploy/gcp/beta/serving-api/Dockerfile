# Configuration-only layer over the accepted immutable beta API image.
FROM asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/api@sha256:f2e73ca98ba915e29a4dd7dc429e34a165475faa7f9000bc8cefaa10e5a6ee4f
COPY --chown=0:0 --chmod=0444 api-host-config.json /opt/ocean/beta-host-config.json
COPY --chown=0:0 --chmod=0444 serving-manifest.json /opt/ocean/serving-manifest.json
ENV OCEAN_V1_HOST_CONFIG=/opt/ocean/beta-host-config.json
