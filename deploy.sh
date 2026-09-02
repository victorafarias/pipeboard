#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="/root/pipeboard"
REPO_URL="git@github.com:victorafarias/pipeboard.git"

echo "==> Deploying Pipeboard MCP to ${DEPLOY_DIR}"

if [ ! -d "${DEPLOY_DIR}/.git" ]; then
  git clone "${REPO_URL}" "${DEPLOY_DIR}"
else
  git -C "${DEPLOY_DIR}" pull --ff-only
fi

cd "${DEPLOY_DIR}"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit META_APP_ID / META_APP_SECRET if needed."
fi

docker compose build --pull
docker compose up -d

echo "==> Waiting for container health..."
for i in $(seq 1 30); do
  status="$(docker inspect -f '{{.State.Health.Status}}' pipeboard-mcp 2>/dev/null || echo starting)"
  if [ "${status}" = "healthy" ]; then
    echo "Container is healthy."
    break
  fi
  sleep 2
done

docker compose ps
echo
echo "Pipeboard MCP should be available at: https://pipeboard.ovictorfarias.com.br/mcp/"
echo "Authenticate requests with: Authorization: Bearer <your_meta_access_token>"
