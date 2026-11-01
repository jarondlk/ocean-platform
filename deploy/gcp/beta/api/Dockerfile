# Generated context only: prepare_context.py refuses uncommitted source bytes.
# Official library/python index read from registry-1.docker.io on 2026-11-02 JST.
FROM python:3.12.15-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEPLOYMENT_ENV=production ENABLE_V1_RESEARCH_CONTROLLER=false \
    ENABLE_V1_RESEARCH_DISPATCH=false ENABLE_V1_SYNTHESIS=false \
    ENABLE_V1_EXPERIMENT_DISPATCH=false
WORKDIR /opt/ocean
COPY requirements/runtime.txt /tmp/runtime.txt
RUN python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r /tmp/runtime.txt \
    && rm /tmp/runtime.txt \
    && groupadd --gid 10001 ocean \
    && useradd --uid 10001 --gid 10001 --no-log-init --create-home ocean
COPY application/ /opt/ocean/
COPY entry.py /opt/ocean/beta_entry.py
COPY source-manifest.json /opt/ocean/source-manifest.json
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["python", "/opt/ocean/beta_entry.py"]
CMD ["serve"]
