FROM asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/context-operator@sha256:a9be3b94b156c9d1260c609fb5958c4e503772d3564b95c097fa9f3d47bb1340
COPY --chown=0:0 --chmod=0444 controller_credential.py controller-credential-manifest.json /opt/ocean/
USER 10001:10001
ENTRYPOINT ["python", "/opt/ocean/controller_credential.py"]
CMD []
