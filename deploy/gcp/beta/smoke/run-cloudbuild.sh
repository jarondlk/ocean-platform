#!/usr/bin/env bash
# Bounded build-only runner. Subject images retain their own non-root defaults.
set -euo pipefail
[[ "${SMOKE_RUNNER:?}" =~ ^ocean-beta-smoke-runner-[a-f0-9-]+$ ]]
[[ "${SMOKE_API:?}" =~ ^asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/api@sha256:[a-f0-9]{64}$ ]]
[[ "${SMOKE_FRONTEND:?}" =~ ^asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/frontend@sha256:[a-f0-9]{64}$ ]]
cleanup() {
  docker cp "${SMOKE_RUNNER}:/tmp/container-smoke-receipt.json" /workspace/container-smoke-receipt.json || true
  docker rm -f "${SMOKE_RUNNER}" >/dev/null 2>&1 || true
}
trap cleanup EXIT
docker pull "${SMOKE_API}"
docker pull "${SMOKE_FRONTEND}"
docker create --name "${SMOKE_RUNNER}" --user 0 --network none \
  --volume /var/run/docker.sock:/var/run/docker.sock --entrypoint python \
  "${SMOKE_API}" /tmp/container_smoke.py \
  --frontend-image "${SMOKE_FRONTEND}" --api-image "${SMOKE_API}" \
  --revision "${SMOKE_REVISION:?}" \
  --frontend-manifest-sha256 "${SMOKE_FRONTEND_MANIFEST:?}" \
  --api-manifest-sha256 "${SMOKE_API_MANIFEST:?}" \
  --output /tmp/container-smoke-receipt.json
docker cp /workspace/container_smoke.py "${SMOKE_RUNNER}:/tmp/container_smoke.py"
docker cp "$(command -v docker)" "${SMOKE_RUNNER}:/usr/local/bin/docker"
docker start --attach "${SMOKE_RUNNER}"
