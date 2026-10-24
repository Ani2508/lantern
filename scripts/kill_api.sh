#!/usr/bin/env bash
set -euo pipefail
ACTION="${1:-}"
FUNCTION_NAME="${FN_API:-lantern-dev-api}"
REGION="${AWS_REGION:-us-east-1}"
if [[ "$ACTION" == "off" ]]; then
  echo "Setting reserved concurrency of $FUNCTION_NAME to 0 (kill switch)"
  aws lambda put-function-concurrency --function-name "$FUNCTION_NAME" --reserved-concurrent-executions 0 --region "$REGION"
elif [[ "$ACTION" == "on" ]]; then
  echo "Clearing reserved concurrency of $FUNCTION_NAME (API on)"
  aws lambda delete-function-concurrency --function-name "$FUNCTION_NAME" --region "$REGION"
else
  echo "usage: $0 on|off" >&2
  exit 2
fi
