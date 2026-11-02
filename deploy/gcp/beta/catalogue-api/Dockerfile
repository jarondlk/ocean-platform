# Source-bound catalogue integration over the exact accepted serving API image.
FROM asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/serving-api@sha256:28f769ee6b44cb46b10c936f045e609bb83ad9d9bc8ccefa98603801a52157ab
COPY --chown=0:0 --chmod=0444 application/api/v1_host.py /opt/ocean/api/v1_host.py
COPY --chown=0:0 --chmod=0444 application/api/v1_catalogue_host.py /opt/ocean/api/v1_catalogue_host.py
COPY --chown=0:0 --chmod=0444 source-manifest.json /opt/ocean/source-manifest.json
COPY --chown=0:0 --chmod=0444 beta-host-config.json /opt/ocean/beta-host-config.json
COPY --chown=0:0 --chmod=0444 empty-catalogue.json /opt/ocean/beta-empty-catalogue.json
COPY --chown=0:0 --chmod=0444 catalogue-serving-manifest.json /opt/ocean/catalogue-serving-manifest.json
ENV OCEAN_V1_HOST_CONFIG=/opt/ocean/beta-host-config.json OCEAN_V1_CATALOGUE_CONFIG=/opt/ocean/beta-empty-catalogue.json
