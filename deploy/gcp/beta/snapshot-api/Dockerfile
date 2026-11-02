# Exact catalogue image plus explicitly committed read-only snapshot integration.
FROM asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/catalogue-api@sha256:0de4842308efeef1b64c3e51b9c225d2ce0dbdd5b4b321ea4c65c1b6e37de13d
COPY --chown=0:0 --chmod=0444 application/api/v1_host.py /opt/ocean/api/v1_host.py
COPY --chown=0:0 --chmod=0444 application/api/v1_catalogue_host.py /opt/ocean/api/v1_catalogue_host.py
COPY --chown=0:0 --chmod=0444 application/ingestion/gcs_catalogue_snapshot.py /opt/ocean/ingestion/gcs_catalogue_snapshot.py
COPY --chown=0:0 --chmod=0444 application/api/v1_beta_research_host.py /opt/ocean/api/v1_beta_research_host.py
COPY --chown=0:0 --chmod=0444 application/ingestion/beta_catalogue_retention.py /opt/ocean/ingestion/beta_catalogue_retention.py
COPY --chown=0:0 --chmod=0444 source-manifest.json /opt/ocean/source-manifest.json
COPY --chown=0:0 --chmod=0444 beta-host-config.json /opt/ocean/beta-host-config.json
COPY --chown=0:0 --chmod=0444 catalogue-source.json /opt/ocean/beta-catalogue-source.json
COPY --chown=0:0 --chmod=0444 snapshot-serving-manifest.json /opt/ocean/snapshot-serving-manifest.json
ENV OCEAN_V1_HOST_CONFIG=/opt/ocean/beta-host-config.json OCEAN_V1_CATALOGUE_MODE=sealed-gcs-v1 OCEAN_V1_CATALOGUE_CONFIG=/opt/ocean/beta-catalogue-source.json
