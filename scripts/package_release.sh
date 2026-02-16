#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
ASSET_NAME="jvc_dla_wifi_bridge.zip"
INTEGRATION_DIR="${ROOT_DIR}/custom_components/jvc_dla_wifi_bridge"

if [[ ! -d "${INTEGRATION_DIR}" ]]; then
  echo "Integration directory not found: ${INTEGRATION_DIR}" >&2
  exit 1
fi

rm -rf "${DIST_DIR}"
mkdir -p "${DIST_DIR}/custom_components"

cp -R "${INTEGRATION_DIR}" "${DIST_DIR}/custom_components/"
find "${DIST_DIR}" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "${DIST_DIR}" -type f -name "*.pyc" -delete

(
  cd "${DIST_DIR}"
  zip -r "${ASSET_NAME}" custom_components >/dev/null
)

echo "Created release artifact: ${DIST_DIR}/${ASSET_NAME}"
