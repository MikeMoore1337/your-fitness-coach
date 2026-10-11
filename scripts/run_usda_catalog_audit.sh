#!/usr/bin/env bash
# Quarterly review-only USDA audit. Never imports or changes the YFC database.
set -Eeuo pipefail
umask 077

YFC_ROOT=/srv/yfc/fit-mini-app
CATALOG_DIR=/srv/yfc/backups/food_catalog
BASELINE="$CATALOG_DIR/usda_reviewed_approved.json"
LOCK="$CATALOG_DIR/usda_audit.lock"
CONTAINER=fit-mini-app-backend-1
RELEASE="$YFC_ROOT/current"

test -r "$BASELINE"
test -d "$RELEASE/scripts"
mkdir -p "$CATALOG_DIR/audits"
chmod 700 "$CATALOG_DIR/audits"
exec 9>"$LOCK"
flock -n 9 || { echo "USDA_AUDIT=ALREADY_RUNNING"; exit 0; }
test "$(docker inspect --format '{{.State.Health.Status}}' "$CONTAINER")" = healthy

NOW="$(date -u +%Y%m%dT%H%M%SZ)"
RUN="$CATALOG_DIR/audits/$NOW"
mkdir -m 700 "$RUN"
TEMP="/tmp/yfc_usda_audit_$NOW"
docker exec -u root "$CONTAINER" mkdir -m 700 "$TEMP"

for f in audit_usda_catalog.py export_usda_reviewed_catalog.py compare_usda_reviewed_catalogs.py; do
  docker cp "$RELEASE/scripts/$f" "$CONTAINER:$TEMP/$f"
done
docker cp "$BASELINE" "$CONTAINER:$TEMP/baseline.json"
docker exec -u root "$CONTAINER" chown -R 10001:10001 "$TEMP"
docker exec -u root "$CONTAINER" chmod 700 "$TEMP"
docker exec -u root "$CONTAINER" sh -c 'chmod 600 "$1"/*' _ "$TEMP"

set +e
docker exec "$CONTAINER" python "$TEMP/audit_usda_catalog.py" \
  --baseline "$TEMP/baseline.json" \
  --candidate "$TEMP/candidate.json" \
  --report "$TEMP/report.json"
RESULT=$?
set -e

docker cp "$CONTAINER:$TEMP/report.json" "$RUN/report.json" || true
docker cp "$CONTAINER:$TEMP/candidate.json" "$RUN/candidate.json" || true
chmod 600 "$RUN/"*.json 2>/dev/null || true
docker exec -u root "$CONTAINER" rm -rf "$TEMP" || true

printf 'USDA_AUDIT_RUN=%s EXIT=%s\n' "$NOW" "$RESULT"
if [ "$RESULT" -eq 2 ]; then
  echo 'USDA_AUDIT=NEEDS_REVIEW; no DB writes, inspect report.json'
elif [ "$RESULT" -ne 0 ]; then
  echo 'USDA_AUDIT=FAILED; baseline unchanged'
else
  echo 'USDA_AUDIT=UNCHANGED'
fi
exit "$RESULT"
