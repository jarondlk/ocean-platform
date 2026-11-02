# Accepted password-safe operator source8e2a163; no mutable base or credentials.
FROM asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/operator@sha256:0a89057b7459342e191e4b194628bee00cc7544749489df9f85f31508399e7b3
USER 0:0
COPY context_operator.py /opt/ocean/context_operator.py
COPY context-operator-manifest.json /opt/ocean/context-operator-manifest.json
RUN chmod 0444 /opt/ocean/context_operator.py /opt/ocean/context-operator-manifest.json
USER 10001:10001
ENTRYPOINT ["python", "/opt/ocean/context_operator.py"]
CMD []
