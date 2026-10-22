#!/usr/bin/env bash
# Usage: pull-api-image.sh <repository:tag>
# Pulls the image from ECR unless the host already has it. It exists because a replaced host has no
# images, so the API unit pulls the last deployed one by itself at boot.
set -euo pipefail

image="${1:?usage: pull-api-image.sh <repository:tag>}"

# REGION and ECR_REPOSITORY_URL.
# shellcheck source=/dev/null
source /opt/cragmatch/host-settings

if docker image inspect "$image" > /dev/null 2>&1; then
  exit 0
fi

# The registry is the part of the repository URL before the first slash.
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${ECR_REPOSITORY_URL%%/*}"
docker pull "$image"
