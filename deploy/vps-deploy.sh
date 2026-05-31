#!/usr/bin/env bash
# This script lives on the VPS at /srv/portal-apps/franklin-housing/deploy.sh,
# is owned by root (mode 0750), and is the *only* thing the GitHub Actions
# deploy SSH key is allowed to execute. Two layers enforce that:
#   1. ~john/.ssh/authorized_keys for the deploy key uses
#        command="sudo /srv/portal-apps/franklin-housing/deploy.sh"
#   2. /etc/sudoers.d/franklin-housing-deploy grants john NOPASSWD for that one
#      script and env_keep's SSH_ORIGINAL_COMMAND through.
#
# It accepts a single argument: the immutable image tag to deploy
# (e.g. "sha-abc1234"), passed via $SSH_ORIGINAL_COMMAND. The strict regex
# guards against command injection — only valid `sha-<hex>` tags are accepted.
set -euo pipefail

SHA="${SSH_ORIGINAL_COMMAND:-}"

if [[ ! "$SHA" =~ ^sha-[0-9a-f]{7,40}$ ]]; then
  echo "Invalid or missing image tag. Expected sha-<hex>, got: '$SHA'" >&2
  exit 1
fi

cd /srv/portal-apps/franklin-housing

# Pin the compose file to the exact SHA we're deploying. If the line already
# matches (re-deploy of the same SHA), sed is a no-op and we still proceed.
sed -i "s|franklin-county-data-pull:[^[:space:]]*|franklin-county-data-pull:${SHA}|" docker-compose.yml

docker compose pull app
docker compose up -d --no-deps app
docker image prune -f
