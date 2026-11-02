# Exact accepted independent API artifact; no mutable base or secret build args.
FROM asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/api@sha256:f2e73ca98ba915e29a4dd7dc429e34a165475faa7f9000bc8cefaa10e5a6ee4f
USER 0:0
COPY enroll.py /opt/ocean/beta_enroll.py
COPY enrollment-manifest.json /opt/ocean/enrollment-manifest.json
USER 10001:10001
ENTRYPOINT ["python", "/opt/ocean/beta_enroll.py"]
CMD []
