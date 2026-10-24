#!/usr/bin/env bash
# Demo step 7: switch the main app off / on.  OWNER: M1.   bash scripts/kill_api.sh off|on
set -euo pipefail
P="--profile ${AWS_PROFILE:-lantern} --region ${AWS_REGION:-us-east-1}"
case "${1:-}" in
  off) aws lambda put-function-concurrency --function-name lantern-dev-api --reserved-concurrent-executions 0 $P >/dev/null
       echo "API OFF - dashboard will fail; fallback page + SMS still work" ;;
  on)  aws lambda delete-function-concurrency --function-name lantern-dev-api $P
       echo "API ON" ;;
  *)   echo "usage: $0 off|on"; exit 1 ;;
esac
