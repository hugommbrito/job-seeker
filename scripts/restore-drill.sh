#!/bin/bash
# Restore drill: prove that a backup can be turned back into a working database.
#
#   scripts/restore-drill.sh path/to/jobseeker.dump
#
# The backup is a single-database archive in pg_dump's custom format, which is what the
# scheduled backup produces. Such an archive contains no roles, so the drill follows the real
# recovery order: bootstrap the roles, restore, verify.
#
# It runs in a scratch container that is removed at the end and never connects to a live
# database. What it verifies is what matters after a restore: the data is there, row-level
# security came back forced on every tenant table, and the app role still sees nothing without
# a user and only one user's rows with one.
#
# Needs Docker. Prints a report to paste into docs/operations/restore-drills.md.
set -euo pipefail

dump="${1:?usage: scripts/restore-drill.sh path/to/jobseeker.dump}"
image="${POSTGRES_IMAGE:-pgvector/pgvector:pg18}"
root="$(cd "$(dirname "$0")/.." && pwd)"
name="job-seeker-restore-drill-$$"

if [ "$(head -c 5 "$dump")" != "PGDMP" ]; then
  echo "restore-drill: $dump is not a pg_dump custom-format archive" >&2
  exit 2
fi

# Throwaway credentials: they exist only inside the scratch container.
secret() { head -c 18 /dev/urandom | base64 | tr -dc 'A-Za-z0-9'; }
super_pw="$(secret)"; migrator_pw="$(secret)"; app_pw="$(secret)"

cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT

started=$(date +%s)
docker run -d --name "$name" -e POSTGRES_PASSWORD="$super_pw" "$image" >/dev/null
for _ in $(seq 1 60); do
  # The image starts a temporary server during init; wait for the real one, on TCP.
  if docker exec "$name" pg_isready -h 127.0.0.1 -U postgres >/dev/null 2>&1; then break; fi
  sleep 1
done

sql() { docker exec -i "$name" psql -X -v ON_ERROR_STOP=1 -U postgres -d jobseeker -At "$@"; }
as_app() {
  docker exec -i -e PGPASSWORD="$app_pw" "$name" \
    psql -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -U app -d jobseeker -At "$@"
}

echo "1/3 bootstrap (roles, database, extensions)"
docker exec -i -e MIGRATOR_DB_PASSWORD="$migrator_pw" -e APP_DB_PASSWORD="$app_pw" \
  "$name" bash -s < "$root/infra/postgres/bootstrap.sh" >/dev/null

echo "2/3 restore"
docker exec -i "$name" pg_restore -U postgres -d jobseeker --exit-on-error < "$dump"

echo "3/3 verify"
failures=0
check() { if [ "$1" = "$2" ]; then echo "  ok   $3"; else echo "  FAIL $3 (got '$1', expected '$2')"; failures=$((failures + 1)); fi; }

migrations="$(sql -c 'SELECT count(*) FROM django_migrations')"
users="$(sql -c 'SELECT count(*) FROM accounts_user')"
[ "$migrations" -gt 0 ] && echo "  ok   $migrations migrations recorded" || { echo "  FAIL no migrations"; failures=$((failures + 1)); }
echo "  info $users user(s) restored"

tenant_tables="$(sql -c "SELECT tablename FROM pg_policies WHERE schemaname = 'public' AND policyname = 'tenant_isolation' ORDER BY 1")"
[ -n "$tenant_tables" ] || { echo "  FAIL no tenant table carries the isolation policy"; failures=$((failures + 1)); }

for table in $tenant_tables; do
  forced="$(sql -c "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname = '$table'")"
  check "$forced" "t" "$table: row-level security is forced"

  total="$(sql -c "SELECT count(*) FROM \"$table\"")"
  blind="$(as_app -c "SELECT count(*) FROM \"$table\"")"
  check "$blind" "0" "$table: the app role sees none of the $total row(s) without a user"

  if [ "$total" -gt 0 ]; then
    owner="$(sql -c "SELECT user_id FROM \"$table\" ORDER BY user_id LIMIT 1")"
    expected="$(sql -c "SELECT count(*) FROM \"$table\" WHERE user_id = $owner")"
    # -q drops the BEGIN/COMMIT tags, so the last line is the SELECT's answer.
    seen="$(as_app -q <<SQL | tail -1
BEGIN;
SELECT set_config('app.user_id', '$owner', true);
SELECT count(*) || ':' || count(*) FILTER (WHERE user_id <> $owner) FROM "$table";
COMMIT;
SQL
)"
    check "$seen" "$expected:0" "$table: as one user, the app role sees that user's rows only"
  fi
done

owner_of_tables="$(sql -c "SELECT string_agg(DISTINCT tableowner, ',') FROM pg_tables WHERE schemaname = 'public'")"
check "$owner_of_tables" "migrator" "every table is owned by migrator"

elapsed=$(( $(date +%s) - started ))
echo
echo "archive:  $(basename "$dump") ($(du -h "$dump" | cut -f1 | tr -d ' '))"
echo "image:    $image"
echo "duration: ${elapsed}s"
if [ "$failures" -gt 0 ]; then
  echo "result:   FAILED ($failures check(s))"
  exit 1
fi
echo "result:   PASSED"
