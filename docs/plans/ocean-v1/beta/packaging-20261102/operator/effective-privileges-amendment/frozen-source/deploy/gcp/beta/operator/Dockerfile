# prepare_context.py accepts only the exact beta API registry with a SHA256 digest.
ARG API_IMAGE
FROM ${API_IMAGE}
USER 0:0
COPY operator.py /opt/ocean/beta_operator.py
COPY operator-manifest.json /opt/ocean/operator-manifest.json
USER 10001:10001
ENTRYPOINT ["python", "/opt/ocean/beta_operator.py"]
CMD []
