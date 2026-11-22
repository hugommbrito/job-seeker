#!/bin/bash
# Creates what a migration cannot: login roles (their passwords are secrets), the databases and
# the extensions that need a superuser. Everything else (grants, row-level security) is a Django
# migration. See docs/adr/0002-database-bootstrap-outside-migrations.md.
#
# Idempotent: run it again to rotate a password or to add the litellm database later.
#
# Runs in two ways:
#   * automatically, as /docker-entrypoint-initdb.d/ script of the postgres image (first start);
#   * by hand or in CI, against a running server, with the usual libpq variables
#     (PGHOST, PGPORT, PGUSER, PGPASSWORD) pointing at a superuser.
#
# Required:  MIGRATOR_DB_PASSWORD, APP_DB_PASSWORD
# Optional:  BACKUP_DB_PASSWORD    gives the read-only backup role a login
#            LITELLM_DB_PASSWORD   creates the litellm role and database (Phase 1)
#            MIGRATOR_CREATEDB=1   lets migrator create test databases (development and CI only)
set -e

: "${MIGRATOR_DB_PASSWORD:?MIGRATOR_DB_PASSWORD is required}"
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD is required}"

admin_user="${PGUSER:-${POSTGRES_USER:-postgres}}"
createdb_attr="NOCREATEDB"
if [ "${MIGRATOR_CREATEDB:-0}" = "1" ]; then
  createdb_attr="CREATEDB"
fi

args=(
  --no-psqlrc
  -v ON_ERROR_STOP=1
  -v "migrator_password=${MIGRATOR_DB_PASSWORD}"
  -v "app_password=${APP_DB_PASSWORD}"
  -v "migrator_createdb=${createdb_attr}"
)
if [ -n "${BACKUP_DB_PASSWORD:-}" ]; then
  args+=(-v "backup_password=${BACKUP_DB_PASSWORD}")
fi
if [ -n "${LITELLM_DB_PASSWORD:-}" ]; then
  args+=(-v "litellm_password=${LITELLM_DB_PASSWORD}")
fi

psql "${args[@]}" --username "$admin_user" --dbname postgres <<'SQL'
-- Roles. Created without attributes first so the statements below are the single place that
-- states what each role may do, whether the role is new or already existed.
SELECT format('CREATE ROLE %I', role_name)
FROM unnest(ARRAY['migrator', 'app', 'backup']) AS role_name
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = role_name)
\gexec

-- migrator owns the schema and is used only by the one-shot migrate service.
ALTER ROLE migrator WITH LOGIN NOSUPERUSER NOCREATEROLE NOBYPASSRLS :migrator_createdb
  PASSWORD :'migrator_password';

-- app is the only role the api and the workers connect as. It owns nothing and cannot bypass
-- row-level security, so a missing WHERE clause cannot cross tenants.
ALTER ROLE app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS
  PASSWORD :'app_password';

-- backup reads everything and writes nothing. pg_dump needs BYPASSRLS to see every tenant's rows.
ALTER ROLE backup WITH NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE BYPASSRLS;
GRANT pg_read_all_data TO backup;
\if :{?backup_password}
  ALTER ROLE backup WITH LOGIN PASSWORD :'backup_password';
\endif

-- Extensions go into template1 before any database is created, so that test databases created
-- by migrator inherit them. vector cannot be created by a non-superuser.
\connect template1
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

\connect postgres
SELECT 'CREATE DATABASE jobseeker OWNER migrator'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'jobseeker')
\gexec

REVOKE ALL ON DATABASE jobseeker FROM PUBLIC;
GRANT CONNECT ON DATABASE jobseeker TO app, backup;

-- Covers a jobseeker database that predates the template1 step.
\connect jobseeker
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

\if :{?litellm_password}
  \connect postgres
  SELECT 'CREATE ROLE litellm'
  WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'litellm')
  \gexec
  ALTER ROLE litellm WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS
    PASSWORD :'litellm_password';
  SELECT 'CREATE DATABASE litellm OWNER litellm'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'litellm')
  \gexec
  -- The gateway's role can reach its own database and nothing else.
  REVOKE ALL ON DATABASE litellm FROM PUBLIC;
\endif
SQL

echo "bootstrap: roles, databases and extensions are in place"
