# Deploy runbook

How the app is deployed on a single server managed by Coolify, and how to check that a deploy is
sound. The reasoning behind the layout is in
[ADR 0004](../adr/0004-deployment-topology-on-coolify.md).

**Status on 2026-11-24: deployed, and section 5 passed** (`verify`, the smoke test with two
users and HSTS on, `make hygiene`, and a browser sign-in). Before the server existed, the image,
`migrate` followed by `api`, the mounted credential, `api` refusing that credential and
bootstrap-then-restore were rehearsed locally with Docker. The Coolify-specific steps were
written from Coolify's documentation (version 4.7); the server runs 4.3.23, and the steps below
are corrected where the first deploy found them wrong. Rows still marked **verify** were not
checked on that deploy.

## 0. Server facts: go or no-go

Run these on the server before anything else. Everything below assumes the answers.

```sh
uname -m                                   # architecture
nproc                                      # CPU cores
free -h                                    # memory, total and available
df -h / /var/lib/docker                    # disk
docker version --format '{{.Server.Version}}'
```

The Coolify version is shown at the top of its sidebar, and on every container it deploys:
`docker inspect <container> --format '{{index .Config.Labels "coolify.version"}}'`.

| Fact | Needed | Found on 2026-11-22 |
| --- | --- | --- |
| Architecture | `x86_64` or `aarch64`; the image builds on either | `aarch64`, the architecture the local rehearsal built and ran on |
| CPU cores | 2 or more (Coolify's own minimum) | 2 |
| Memory available with Coolify running | About 1 GB for Phase 0 (Postgres and two web workers). The full service list in the plan (Redis, two workers, the scheduler, the model gateway) needs roughly 3 GB more. Both figures are estimates: measure with `docker stats` after the first deploy | 9.0 GiB available of 11 GiB, and 4 GiB of swap unused |
| Free disk | 10 GB or more; each build keeps a Node layer and a Python layer | 23 GB free of 49 GB. Docker's data directory is on the root filesystem, so images, the build cache, the database volume and local backup copies all draw on it |
| Coolify | 4.x | 4.3.23, with Traefik 3.6 as its proxy |

**Go** on every row.

**No-go** if memory or disk is short: fix that first, because a build that runs the server out
of memory takes Coolify down with it.

## 1. Database

1. In Coolify, create a **PostgreSQL** database resource and choose the **PGVector 18** image
   (`pgvector/pgvector:pg18`). Keep the generated superuser password in Coolify. Do not give the
   database a public port.
2. Start it, then create the roles, the `jobseeker` database and the extensions. From a checkout
   of this repository on the server, with two new passwords of your choosing:

   ```sh
   read -rs MIGRATOR_DB_PASSWORD && read -rs APP_DB_PASSWORD
   docker exec -i \
     -e MIGRATOR_DB_PASSWORD="$MIGRATOR_DB_PASSWORD" -e APP_DB_PASSWORD="$APP_DB_PASSWORD" \
     <database-container> bash -s < infra/postgres/bootstrap.sh
   ```

   The script is idempotent. Run it again later with `LITELLM_DB_PASSWORD` set to add the model
   gateway's database (Phase 1), or with new values to rotate a password.
3. Note the database's internal hostname from Coolify's **internal URL** for the resource. The
   two DSNs used below are:

   ```
   postgres://migrator:<password>@<internal-host>:5432/jobseeker
   postgres://app:<password>@<internal-host>:5432/jobseeker
   ```

## 2. The schema owner's credential

Coolify gives every variable set in its UI to every service of a compose application, so the
`migrator` DSN must not be one. It is a file on the server, mounted into the `migrate` service
only. The container runs as uid 999.

```sh
sudo install -d -m 700 -o 999 -g 999 /data/job-seeker/secrets
sudo sh -c 'umask 077; cat > /data/job-seeker/secrets/migrator_database_url'   # paste the DSN, Ctrl-D
sudo chown 999:999 /data/job-seeker/secrets/migrator_database_url
sudo chmod 400 /data/job-seeker/secrets/migrator_database_url
```

## 3. Application

1. Create an **Application** from the Git repository with the **Docker Compose** build pack.
   - Base Directory: `/`
   - Docker Compose Location: `/infra/docker-compose.coolify.yml`
2. Under **Advanced**, enable **Connect to Predefined Network**, so the services can reach the
   database resource.
3. Add the domain to the `api` service with the container port as a suffix, for example
   `https://jobs.example.org:8000`. Coolify's proxy issues the certificate. A compose
   application has one domain field per service; if the services are not listed, press
   **Reload Compose File**. Leave `migrate` without a domain. The domain reaches the proxy only
   through labels written at deploy time, so saving the field is not enough: **Redeploy**.
4. Set the variables:

   | Variable | Value |
   | --- | --- |
   | `DJANGO_SECRET_KEY` | 50 or more random characters: `python3 -c "import secrets; print(secrets.token_urlsafe(64))"` |
   | `DJANGO_ALLOWED_HOSTS` | The public hostname only: `jobs.example.org`, with no scheme, port or trailing slash |
   | `APP_DATABASE_URL` | The `app` DSN from step 1 |
   | `TRUSTED_PROXY_COUNT` | `1`; `2` if a CDN sits in front of Coolify's proxy |
   | `DJANGO_HSTS_SECONDS` | `0` for the first deploy; `31536000` once HTTPS is confirmed |

5. Deploy. `migrate` runs and exits; `api` starts after it and becomes healthy when `/health`
   answers.

**Verify on the first deploy**, and use the fallback if it does not hold:

| Assumption | How to check | Fallback |
| --- | --- | --- |
| `api` waits for `migrate` (`depends_on` with `service_completed_successfully`) | The `migrate` container's log shows the migrations before `api`'s first log line | Run migrations by hand before each deploy that has them: `docker run --rm --network coolify -e DJANGO_SECRET_KEY=unused -e DATABASE_URL_FILE=/run/secrets/migrator_database_url -v /data/job-seeker/secrets/migrator_database_url:/run/secrets/migrator_database_url:ro <image> migrate` |
| The absolute bind mount reaches `migrate` unchanged | `migrate` connects; a missing file fails with "No such file" | Same command as above, and remove the `migrate` service from the compose file |
| The schema owner's DSN is absent from `api` | `docker exec <api-container> env \| grep -c migrator` prints `0` | Do not proceed until it does |
| The finished `migrate` container does not mark the deployment unhealthy (`exclude_from_hc`) | The deployment shows as healthy | Same as the first row |

**When the site does not answer**, while `api` shows as healthy. Its health check calls
`localhost` from inside the container, so it passes even when no outside request can reach the
app.

| Symptom from outside | Cause | Fix |
| --- | --- | --- |
| The certificate is `CN=TRAEFIK DEFAULT CERT`; HTTP gives 404 | The proxy has no route for the host: `docker inspect <api-container>` shows no `traefik.*` label | Set the domain on the `api` service and redeploy (step 3). A container created before the change still lacks the labels |
| Every path, `/health` included, gives an empty `Bad Request (400)` from gunicorn | Django rejects the `Host` header: `DJANGO_ALLOWED_HOSTS` is missing the hostname or carries a scheme or port | Correct the variable and redeploy |

## 4. Users

There is no sign-up. Create each account from the `api` container; the password is prompted for
and never passed as an argument:

```sh
docker exec -it <api-container> entrypoint manage create_user someone@example.org --role owner
docker exec -it <api-container> entrypoint manage create_user other@example.org --role member
```

## 5. Acceptance

Run after the first deploy and after any change to tenancy, authentication or the deployment.

```sh
# On the server: the role, the classification of every table, and the policy on every tenant
# table, as the database really enforces them. Read-only.
docker exec <api-container> entrypoint manage verify

# From your own machine: the public surface and a real sign-in for each user.
scripts/smoke.py https://jobs.example.org --user someone@example.org --user other@example.org

# From your own machine: nothing personal, no stray document and no personal email anywhere in
# the git history.
make hygiene
```

Run `verify` after creating the users. Its last check counts the tenant rows readable with no
user set, and it only tests something once tenant rows exist: in Phase 0 nothing writes a
profile, so it reports 0 on an empty table. The role and policy checks are what it proves until
then.

`smoke.py` requires the HSTS header on an `https://` URL, so it reports one failure while
`DJANGO_HSTS_SECONDS` is `0`. That is the signal to raise it: every other check passing means
HTTPS works. If it fails at once with `CERTIFICATE_VERIFY_FAILED: unable to get local issuer
certificate`, the local Python has no CA certificates (the python.org installer on macOS ships
without them): run `Install Certificates.command` from its folder in `/Applications`. A
`self signed certificate` error instead is the server's: see the table in section 3.

The catalog meta-test and the canary isolation suite run on every commit in CI against a real
Postgres, as the `app` role. `verify` applies the same catalog rules to the deployed database.

Then open the site in a browser, sign in as each user, and confirm each sees the empty app.

## 6. Backups

1. In Coolify, add an **S3 storage** whose bucket encrypts at rest, with an access key that can
   reach that bucket only. Coolify does not encrypt the archive itself, so encryption has to be
   a property of the destination.
2. On the database resource, add a **scheduled backup** of the `jobseeker` database (daily),
   enable S3, and set retention for both the local and the S3 copies.
3. Run one backup by hand and confirm the object appears in the bucket.
4. Do a restore drill and record it: see [restore-drills.md](restore-drills.md).

A backup of one database is a `pg_dump` archive in custom format. It contains no roles, so
recovery is always: create a database resource, run `bootstrap.sh`, then restore. The archive
is taken by the database's superuser, which row-level security does not filter, so it holds
every user's rows.

## 7. Routine operations

- **Deploy**: push to `main` and deploy from Coolify. Migrations run first, as above.
- **Roll back**: redeploy the previous commit from Coolify. Migrations are not reversed
  automatically; a release that needs a schema rollback says so in its commit message.
- **Rotate a database password**: run `bootstrap.sh` with the new value, then update
  `APP_DATABASE_URL` in Coolify or the file from section 2, and redeploy.
- **Housekeeping**: `entrypoint manage clear_expired` deletes expired sessions and finished
  sign-in throttle windows. It becomes a scheduled task in Phase 1.
- **What runs where**: `/health` says the process is up and touches no database. The `api`
  container refuses to start if its database role could bypass row-level security; if a deploy
  fails at start with an error mentioning `tenancy.E00x`, the DSN is wrong, not the code.
