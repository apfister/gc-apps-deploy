#!/usr/bin/env bash
set -euo pipefail

readonly ARTIFACT_PATH="${1:-dist}"
readonly DEPLOY_ENDPOINT="${GCAPPS_DEPLOY_ENDPOINT:-https://gcapps.esrigcazure.com/_deploy}"
readonly OIDC_AUDIENCE="${GCAPPS_OIDC_AUDIENCE:-https://gcapps.esrigcazure.com/_deploy}"

for command in awk curl find jq tar; do
  command -v "${command}" >/dev/null || {
    echo "${command} is required" >&2
    exit 1
  }
done

: "${ACTIONS_ID_TOKEN_REQUEST_URL:?GitHub OIDC is unavailable; grant permissions: id-token: write}"
: "${ACTIONS_ID_TOKEN_REQUEST_TOKEN:?GitHub OIDC request token is unavailable}"
: "${RUNNER_TEMP:?RUNNER_TEMP is unavailable}"

[[ -d "${ARTIFACT_PATH}" ]] || {
  echo "Artifact path does not exist or is not a directory: ${ARTIFACT_PATH}" >&2
  exit 1
}
[[ -f "${ARTIFACT_PATH}/index.html" && ! -L "${ARTIFACT_PATH}/index.html" ]] || {
  echo "Artifact must contain a regular index.html at its root" >&2
  exit 1
}

unsafe_entry="$(find "${ARTIFACT_PATH}" ! -type d ! -type f -print -quit)"
[[ -z "${unsafe_entry}" ]] || {
  echo "Artifact contains an unsupported entry: ${unsafe_entry}" >&2
  exit 1
}

uncompressed_size="$(find "${ARTIFACT_PATH}" -type f -printf '%s\n' |
  awk '{ total += $1 } END { printf "%.0f", total }')"
archive_path="$(mktemp "${RUNNER_TEMP}/gcapps-artifact.XXXXXX.tar.gz")"
response_path="$(mktemp "${RUNNER_TEMP}/gcapps-response.XXXXXX.json")"
trap 'rm -f "${archive_path}" "${response_path}"' EXIT

tar --create --gzip --hard-dereference \
  --file="${archive_path}" --directory="${ARTIFACT_PATH}" .

if ! oidc_response="$(curl --silent --show-error --fail-with-body --get \
  --header "Authorization: Bearer ${ACTIONS_ID_TOKEN_REQUEST_TOKEN}" \
  --data-urlencode "audience=${OIDC_AUDIENCE}" \
  "${ACTIONS_ID_TOKEN_REQUEST_URL}")"; then
  echo "GitHub OIDC token request failed" >&2
  printf '%s\n' "${oidc_response}" >&2
  exit 1
fi
oidc_token="$(jq -er '.value | select(type == "string" and length > 0)' <<<"${oidc_response}")"
echo "::add-mask::${oidc_token}"

if ! http_status="$(curl --silent --show-error \
  --output "${response_path}" --write-out '%{http_code}' \
  --request POST \
  --header "Authorization: Bearer ${oidc_token}" \
  --header 'Content-Type: application/gzip' \
  --header "X-Artifact-Uncompressed-Size: ${uncompressed_size}" \
  --data-binary "@${archive_path}" \
  "${DEPLOY_ENDPOINT}")"; then
  cat "${response_path}" >&2
  echo "Deployment request failed before receiving an HTTP response" >&2
  exit 1
fi

cat "${response_path}"
case "${http_status}" in
  2??) ;;
  *)
    echo "Deployment failed with HTTP ${http_status}" >&2
    exit 1
    ;;
esac