# Implementation plan

Part A of the planning package closed on 2026-11-21. See the [README](README.md) for how the package is organised and how later decisions are recorded.

## 1. Product summary

A self-hosted job-search assistant for Toronto. It collects postings from public applicant-tracking-system (ATS) APIs and an aggregator, ranks each posting against a user's profile, tracks applications on a kanban, proposes status changes from application emails, and builds a tailored CV per posting. It follows the collect, normalise, rank, notify pattern of the sibling project `rental-searcher` (Toronto Rental Monitor).

Each user has isolated data. Profiles must not assume a tech career: sources, rubric weights and career tracks are per-user data.

Ontario's job-posting rules (in force since 2026-01-01 for employers with 25 or more employees; re-read the legal source cited in the original proposal before coding them) supply ranking signals: a published salary or a range no wider than CAD 50,000 (exempt above CAD 200,000 a year), disclosure of AI use in screening, a statement of whether the vacancy exists, and notice of the hiring decision to interviewed candidates within 45 days of the last interview.

## 2. Project rules

These go into the repository's `CLAUDE.md` and apply to every phase.

1. **No personal data in git, ever.** Real CVs, emails, labels, eval output and Part C live in `private/` (git-ignored). Fixtures are synthetic and use placeholder companies. Screenshots come only from the demo tenant. Public docs, test names, ADRs and commit messages never refer to a real person's job search.
2. **Nothing is discarded silently.** Every eliminated posting records a machine-readable reason. An undeterminable fact is tri-state (`unknown`) and never eliminates.
3. **No `if user_id == ...`.** Anything that differs between users is a database row validated by Pydantic on read. No profile is defined in code.
4. **The model proposes, code decides, a person confirms.** The model returns categorical verdicts with verbatim quotes; the score is computed in code from profile weights. An email never changes a status without approval.
5. **No invented experience.** Every generated CV bullet cites its source bullets and inherits the lowest evidence level among them (`hands_on`, `led`, `supervised`).
6. **Posting and email text is untrusted data** in every sink, not only prompts: model calls over it have no tools and schema-validated output; the UI renders it as text; outbound fetches are guarded (section 3.5).
7. **Official public APIs only.** No scraping of LinkedIn or Indeed. Identifiable User-Agent, a measured gap per source, an immediate pause on 429 or 403, no CAPTCHA or login workarounds.
8. **A model failure never drops work.** No key, an error or a refusal leaves the item marked as not evaluated.
9. **English everywhere:** code, comments, docs, UI, commits. Commits read "Do X, because Y". Comments explain why.

## 3. Architecture

### 3.1 Stack and repository

Backend: Python, Django, Django Ninja (Pydantic schemas, OpenAPI), PostgreSQL with pgvector and `pg_trgm`, Celery with Redis, `httpx`, pytest. Front end: React, Vite, Tailwind, shadcn/ui, dnd-kit, TanStack Query, PWA. Use the current stable Django and CPython at implementation time; dependencies are locked with `uv`.

```
backend/           Django project
  config/          settings, urls, celery app
  apps/            one Django app per domain (list below)
web/               React + Vite + Tailwind + shadcn/ui, PWA
infra/             Dockerfile (multi-stage, multi-arch), docker-compose.dev.yml, litellm/config.example.yaml
demo/              Synthetic persona and demo data
evals/             Label format, synthetic example sets, eval scripts
docs/planning/     Proposal summary, decision log, this plan
docs/adr/          Later decisions
private/           IGNORED: Part C, real seed documents, denylist, real labels, eval output
```

Django apps: `accounts` (custom user, roles, session backend), `tenancy` (tenant context, row-level-security helpers, meta-test), `profiles` (profile, tracks, home location), `companies` (with offices), `sources`, `postings`, `geo` (transit stops, distance), `ranking`, `applications`, `documents`, `llm`, `notifications`, `experience`, `cv`, `mail`, `interview`, `insights`, `operations`.

The API contract is the OpenAPI schema Django Ninja emits. `openapi-typescript` generates the web client's types from it, and CI fails if the generated file is stale. The built SPA is served by Django through WhiteNoise with a catch-all route.

Set `AUTH_USER_MODEL` to the custom user (email as login, `role` field) before the first migration; it cannot be changed cleanly later.

### 3.2 Services (Coolify, one Oracle Cloud server)

One image, a different command per service. Each service is added in the phase that first uses it.

| Service | From | Role and secrets |
| --- | --- | --- |
| `migrate` | Phase 0 | One-shot pre-deploy `manage.py migrate`. Only holder of the `migrator` database role |
| `api` | Phase 0 | Gunicorn serving Django and the static SPA. Database role `app`. Holds no model key; a Django system check refuses to start it if the mailbox private key is in its environment |
| `postgres` | Phase 0 | Postgres with pgvector. Databases `jobseeker` and `litellm` |
| `redis` | Phase 1 | Celery broker |
| `worker` | Phase 1 | Celery worker for source polling, capture fetch, extraction, ranking, notifications and PDF rendering. Holds the budget-capped gateway key |
| `beat` | Phase 1 | Celery beat, exactly one instance, for schedules |
| `litellm` | Phase 1 | Model gateway. Internal network only, no public domain, message logging off |
| `mail-worker` | Phase 4 | Celery worker consuming only the `mail` queue. Sole holder of the mailbox private key. Fetches no user-supplied URL |

The image is Debian-based (`python:*-slim`) because WeasyPrint needs Pango; no browser is installed anywhere.

Files (uploaded and generated documents) are stored in Postgres `bytea` behind a `DocumentStore` interface, so they sit under row-level security and need no extra service; an S3 adapter can be added later. Backups use Coolify's scheduled Postgres backup to an encrypted off-host S3 target.

### 3.3 Database roles and tenancy

A public guest login runs on the same instance as real data, so isolation is a Phase 0 requirement.

- Roles: `migrator` (owns the schema, used only by `migrate`), `app` (non-owner, no `BYPASSRLS`, the only DSN in `api` and the workers), `backup` (read-only), `litellm` (its own database only).
- One entry point, `tenant_context(user_id)`: a context manager that opens `transaction.atomic()` and runs `SELECT set_config('app.user_id', %s, true)`. A middleware wraps every authenticated request in it; Celery tasks and management commands open it explicitly. No network I/O inside it.
- Tables are classified as `catalog`, `tenant` or `framework` (Django's own: users, sessions, migrations, content types, admin log). Every tenant model inherits `TenantModel` (`user` foreign key, not null). Django generates the table migrations; roles, grants, extensions, and `ENABLE` plus `FORCE ROW LEVEL SECURITY` with a policy on `app.user_id` are hand-written `RunSQL` operations through one helper.
- Meta-test over `pg_catalog`: every table is classified; every tenant table is forced and has a policy; the `app` role with no user set reads zero tenant rows. Database tests connect as `app`, never as the owner, or the policies would not fire.
- Authentication: email and password (Django's argon2 hasher), `HttpOnly`/`Secure`/`SameSite=Lax` session cookie, Django CSRF protection with the token sent as a header by the SPA, no public sign-up (users created by a management command), login rate limit. Sessions use a small custom backend that stores only a hash of the session key. The user table holds email, password hash and role, nothing else. Roles: `owner`, `member`, `demo`.
- Demo role, deny by default: a middleware rejects any request from a `demo` session unless the resolved view is marked `demo_readable`. A test walks Django's URL resolver and fails on any unclassified route, including admin and static mounts. The role is also enforced inside the model gateway, notifiers, outbound fetch and upload. The demo tenant contains only synthetic rows in per-user tables and has no watchlist, so it never sees the live catalog. It is rebuilt from `demo/` on deploy.
- Isolation suite built on canaries: tenant B is seeded with unique strings, and no response to tenant A or to the demo role may contain any of them. The guest login is enabled only after this suite and the meta-test pass.
- A user sees catalog postings only through their own watchlist and saved searches, never the whole catalog.
- Django admin is for the `owner` only, registers catalog and operations models only (never tenant models), and is not routed on the public hostname.

### 3.4 Model gateway

- `LlmGateway` wraps the official `anthropic` Python SDK with `base_url` set to LiteLLM's Anthropic-format endpoint. Each task uses an alias from the LiteLLM config: `extractor`, `fit-judge`, `email-classifier`, `writer`. All map to `claude-opus-5-5` until the eval justifies a cheaper model. Only the workers call the gateway; `api` enqueues.
- Structured output through `client.messages.parse()` with a Pydantic model. Adaptive thinking, explicit `output_config.effort` per task (the Opus 5.5 default is `medium`), no sampling parameters. Check `stop_reason` for `refusal` and `max_tokens` before reading content.
- Prompt caching: the stable prefix (rubric plus the user's reviewed evidence summary for one track) sits before the breakpoint, the posting after it. Verify with `usage.cache_read_input_tokens`.
- Idempotency: each response is persisted keyed by (task, entity, prompt version, input hash) before post-processing, so task retries never re-bill.
- Budget: a hard `max_budget` on the LiteLLM virtual key, plus an application-level daily cap of judged postings per user. When a cap is hit, ranking stops after the embedding stage and says so.
- `llm_calls` table: task, model, prompt version, token counts including cache, estimated cost, latency, user, entity, outcome.
- Embeddings: the `openai` Python SDK pointed at the same gateway, alias `embedder`, stored in a pgvector column. Each row records model and dimension so re-embedding is possible.
- Gateway spike at the start of Phase 1, on `claude-opus-5-5`: (a) structured output, (b) `cache_control` with a non-zero cache read on the second call, (c) adaptive thinking with `effort`. Anything that fails moves to LiteLLM's native pass-through route (`/anthropic`), with the model id taken from application config. Server-side refusal fallbacks are tried in the same spike but do not gate it; if the gateway rejects or swallows the parameter, rule 8 covers refusals. Message Batches are deferred until a backfill needs them.
- The implementing session must load the `claude-api` skill before writing any model call (its Python README and tool-use guide, and the SDK upgrade note if the installed SDK is 1.x) and use its `build-eval` flow for section 5.6.

### 3.5 Untrusted content and outbound requests

- Posting and email bodies are rendered as plain text. CSP `script-src 'self'`.
- CV rendering uses Django's auto-escaping templates and WeasyPrint, which runs no JavaScript; its URL fetcher is restricted to bundled fonts and styles.
- URL capture: a URL on a known ATS is resolved through that ATS's API; LinkedIn and Indeed URLs are refused with a prompt to paste the text; any other URL must be https, resolve to a public address, and is re-checked after every redirect.
- HTTP error messages redact query strings, because some sources carry keys there.

## 4. Data model

Shared catalog (no user column):

- `companies`: name, site, `ats_type` (`greenhouse`, `lever`, `ashby`, `none`), `ats_slug`, email domains, tags.
- `company_offices`: company, label, address, latitude, longitude, geocode source, verified date.
- `job_postings`: identity is (`source`, `source_id`). Company, title, raw and normalised location, `workplace_type`, description text, URLs, dates (published, first seen, last seen, closed), `content_hash`, salary (min, max, currency, period, origin `structured`/`text`/`none`), application deadline, language, `raw` JSON. `canonical_posting` links a duplicate seen through another source; rows are never merged.
- `posting_extractions`: one per posting and prompt version, shared by all users (schema in 5.2).
- `posting_embeddings`, `transit_stops`, `source_state` (breaker state, authoritative across processes) and `source_runs`.

Per user (row-level security):

- `profiles`: `hard`, `soft`, `notify` JSON validated by Pydantic; home location as coordinates and a label; timezone. `tracks`: target titles, summary, embedding, filter overrides. `watchlist`, `saved_searches`.
- `user_postings`: manually captured postings, same shape as `job_postings`. Captures never enter the shared catalog.
- `posting_scores`: stage reached, elimination reasons, similarity, per-item verdicts, component values, final score, winning track, prompt version. `posting_feedback`, `golden_labels`, `needs_review`.
- `applications`: stage, outcome, track, dates (`applied_at`, `last_interview_at`, `decision_due_at`), next action, sent documents and `posting_snapshot` (a frozen copy of the posting, with no foreign key to the catalog, so human decisions survive a catalog reset). `application_events`, `contacts`, `documents`.
- `experience_roles`, `experience_bullets` (text, metrics, skills, tracks, `evidence_level`, embedding), `answer_bank`, `cv_builds`.
- `mailboxes` (one sealed blob holding host, port, user and password), `email_messages` (unique on Message-ID), `status_proposals`.
- `notification_channels`, `notifications` with a unique `dedupe_key`.
- `star_stories`, `interview_preps`, `offers`.

## 5. Ranking contract

### 5.1 Stages

1. **Hard filters** from `profiles.hard`, using structured and regex-derived fields only: workplace type, location, salary floor, seniority, employment type, optional commute cap. A filter eliminates only on a known fact and records the reason. Filters run again after extraction, when more facts are known.
2. **Embedding similarity** between the posting (title plus normalised description) and each active track (target titles, summary and reviewed evidence summary). The best track wins.
3. **Judging.** The pool is open postings that pass stage 1 and have no verdict at the current prompt version, ordered by similarity; the top N per user per day are judged (default 20). The first step is the shared extraction, run lazily and reused by every user. The second is the per-user verdict call.

`manage.py rank_stored` recomputes every score from stored verdicts and components with no network call and never notifies. Changing a weight costs nothing.

### 5.2 Shared extraction (model, once per posting)

Requirements, each with an id, a verbatim quote, `must` or `nice`, and a category; stack list; years required; seniority label; languages; on-site days per week; office address quote; salary with quote; AI-screening disclosure and existing-vacancy statement, each `yes`/`no`/`unknown` with quote. Structured source fields always win over text; a conflict is flagged, not resolved.

### 5.3 Per-user verdicts (model, top N only)

For each requirement: `met`, `partial`, `missing` or `unknown`, the ids of the experience bullets that support it, and a verbatim posting quote. One seniority verdict (`below`, `match`, `above`, `unknown`) with quote. A short list of risks shown to the user and not scored. Code checks that every quote is a substring of the posting and every bullet id exists; a failed check turns that item into `unknown`. A bullet at evidence level `supervised` cannot support `met` on a requirement that asks for hands-on implementation.

### 5.4 Score components

The final score is the weighted sum over `profiles.soft.weights`, computed in code. An unknown weight key is an error.

| Key | Computed from |
| --- | --- |
| `mustHaveCoverage` | Verdicts on `must` requirements: met 1, partial 0.5, missing 0, unknown skipped |
| `niceToHaveCoverage` | Same, over `nice` requirements |
| `seniorityFit` | Seniority verdict and years required against the track's evidence |
| `stackOverlap` | Extracted stack against profile skills, set arithmetic |
| `domainMatch` | Company tags against the profile's preferred domains |
| `languageBonus` | Required or preferred languages against profile languages |
| `salaryFit` | Linear decay between the profile's target and floor |
| `transparency` | Salary disclosed, range width within the legal limit, AI disclosure, vacancy statement |
| `ghostRisk` | Repeated description hash across reposts, posting age, repost count |
| `commuteDistance` | Section 5.5 |
| `officeTransit` | Section 5.5 |

A component with no data returns null and leaves both numerator and denominator, except where that would reward ignorance; those cases use the neutral credit described below.

### 5.5 Commute (hybrid and on-site postings)

Offline heuristic, computed in code, never sent to a model or a third party.

- **Transit data.** `transit_stops` seeded from OpenStreetMap through Overpass over a Greater Toronto bounding box, with a mode per stop: `subway`, `light_rail`, `streetcar`, `bus`. The seed fails loudly on a thinned result (minimum counts per mode and per rapid-transit line) and credits OpenStreetMap in the README.
- **Home.** Stored per user as coordinates and a label, set either by dropping a map pin or by geocoding an address once. Never logged, never in fixtures; the demo persona uses a public landmark.
- **Office.** Resolved in order: a street-level address in the posting's structured data; the `company_offices` entry for the posting's city; an address quoted by the extraction and then geocoded; otherwise unknown. City centroids are never used.
- **`commuteDistance`.** Straight-line kilometres from home to office, linear decay between `soft.commute.fullCreditKm` and `soft.commute.zeroAtKm`.
- **`officeTransit`.** A ladder in profile data, first match wins: walking distance (straight line times 1.3) from the office to the nearest stop of each tier, with linear decay inside the tier. Defaults: subway or light rail 1.0, streetcar 0.6, bus 0.3, nothing in range 0.
- **Days on site.** Taken from the extraction when stated, otherwise from the profile default for the workplace type (hybrid 3, on-site 5). Each component becomes `1 - (1 - raw) * days / 5`.
- **Remote** postings score 1 on both. **Unknown office** on a hybrid or on-site posting gets the profile's neutral credit (default 0.5) and a `needs_review` entry, so the user can add the office.
- A `CommuteEstimator` interface keeps a routing API possible later without touching the scorer.

### 5.6 Calibration

- Label schema: fit from 1 to 5 per posting, plus a verdict per must-have requirement.
- The labelled sample is stratified across hard-filter rejects, postings below the embedding cut and the judged top N. Sets are frozen and versioned in `private/evals/`; day-to-day thumbs feed the next version, not the current one.
- `manage.py eval_ranking` reports precision at k, rank correlation and must-have agreement per prompt version and per model, over three repeats with a paired bootstrap.
- Decision rule for a cheaper model: keep `claude-opus-5-5` unless the interval excludes a drop larger than a threshold fixed before the run. With 30 to 50 labels the interval is wide; the tool prints it.
- Small synthetic sets cover the other three tasks (extraction, email classification, CV rewriting).

## 6. Sources

Formats verified against live boards on 2026-11-21, except where noted.

| Source | Endpoint | Notes |
| --- | --- | --- |
| Ashby | `GET api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true` | One call returns every posting with `workplaceType`, `address`, `publishedAt`, `descriptionPlain`. `compensation` can be empty even when the text states a range |
| Greenhouse | List: `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`. Detail: `.../jobs/{id}?pay_transparency=true` | Pay ranges (`pay_input_ranges`, in cents) and `include_ai_disclaimer`/`ai_disclaimer` come only from the detail call, made lazily for postings that pass stage 1. `content` arrives entity-escaped: decode entities before stripping tags. The vacancy statement is in the text only |
| Lever | `api.lever.co/v0/postings/{company}?mode=json` | Not probed; confirm the format |
| Adzuna | `api.adzuna.com/v1/api/jobs/ca/search/{page}` with `app_id` and `app_key` | Not probed; needs registration. Check rate limits, attribution terms and whether descriptions are truncated. If they are, Adzuna is discovery only and judging needs the full text from the ATS or a paste |

Every connector implements one interface, has its own breaker (state in `source_state`; Celery only schedules and spaces the work) and a probe command. Boards are polled every 6 hours with jitter, Adzuna daily. A posting is closed only after it is absent from consecutive runs.

## 7. Phases

Each phase ends usable, with acceptance that can be re-run.

### Phase 0 — Foundation

1. Server facts first, as a go or no-go: `uname -m`, memory, disk, Coolify version. Everything else assumes the answer.
2. Hygiene before the first commit: split this file as described at the top; `.gitignore` for `private/`, `.env`, `.DS_Store`; move existing personal documents into `private/seed/`; set the repository's author email to the GitHub no-reply address after confirming with the owner; pre-commit and commit-msg hooks that reject anything matching `private/denylist.txt`; a CI check that fails on tracked `.pdf`, `.eml` or `.html` outside an allowlist; gitleaks; licence; `CLAUDE.md` with the project rules.
3. Django project and web scaffold; CI for both toolchains (ruff, type check, pytest; eslint, `tsc`, vitest, build; generated API types up to date). CI holds no secrets and never runs probe, verify or eval.
4. Custom user model, database roles, `tenant_context`, `TenantModel` and the row-level-security migration helper, the catalog meta-test, authentication and the hashed-session backend, `create_user`, the demo-guard middleware with the route classification test, and the canary isolation suite.
5. Deploy `migrate`, `api` and `postgres` on Coolify with a domain and HTTPS, `/health`, off-host encrypted backup and one restore drill.

Acceptance: two users log in on the deployed instance and see an empty app; meta-test and isolation suite pass; a hygiene script (denylist and file-type checks over the full history) passes; the restore drill is recorded in `docs/`.

### Phase 1 — Lean tracker

- Add `redis`, `worker`, `beat`, `litellm`; run the gateway spike; `llm_calls` and response persistence.
- Kanban with stages Discovered, Saved, Preparing, Applied, Recruiter, Interviews, Offer, Accepted and outcomes Rejected, Ghosted, Withdrawn. Table view with filters in the URL.
- Card: timeline, contacts, sent documents (upload), next action with a date, posting snapshot.
- Capture: paste text or a URL; extraction runs as a task; the user reviews the fields before saving. Captures go to `user_postings`.
- Import of past applications through the app (form or file upload), so real data never needs a seed script.
- Reminders: next action due; the 45-day clock, counted from a user-confirmed interview date; a follow-up or Ghosted suggestion after N quiet days. Channels: Telegram (one bot, linked per user) and an in-app notification centre. Quiet hours use the user's timezone.
- First-run wizard: profile, tracks, hard filters, home location, channels.
- Demo tenant and guest login. Admin registered for catalog and operations models.

Acceptance: an application is created from a pasted posting in under a minute; each reminder fires exactly once; the guest can browse and every unmarked route answers 403 without logging the guest out.

### Phase 2 — Evidence, discovery and ranking

1. Experience bank first, because the rubric judges against it: import a CV and a profile export through the model, proposing roles and bullets with evidence levels; nothing is saved without the user's review.
2. Connectors for Greenhouse, Lever, Ashby and Adzuna; normalisation, duplicate linking, closure, probe.
3. Watchlist: research about 40 fintech and AI companies hiring in Toronto, validate each ATS slug against the API, record each Toronto office address, and **stop for the owner's approval** before seeding. ATS detection from a careers URL for companies added later.
4. Transit seed, geocoding and the two commute components.
5. Ranking per section 5; feed with the full breakdown, save to board, thumbs, hide company, `needs_review` queue.
6. Labelling screen, `eval_ranking`, per-model report.
7. Email (SMTP) and web-push (VAPID, service worker) channels; daily digest with the five best new postings, follow-ups due and the week's interviews; instant alert above a minimum score.

Acceptance: fixture-based connector tests for each source; a probe run against two live boards recorded in `source_runs`; `rank_stored` is byte-for-byte reproducible; `verify` proves that a closer office never scores lower and that subway, streetcar and bus rank in that order at equal distance; the eval prints its metrics and interval; the digest arrives on all three channels.

### Phase 3 — Application help

- Consistency audit between a user's profile sources (dates, titles), shown as a checklist.
- Posting analysis: requirements and keywords against the bank, coverage and gaps.
- Tailored CV. Bullet selection per track and posting; each rewritten bullet carries `source_bullet_ids` and inherits the lowest evidence level of its sources; code checks a per-level verb list (English and French), blocks numbers or entities absent from the sources, and limits vocabulary to skills tagged on the source bullets. The user approves a diff per bullet before the build becomes "the sent version". HTML/CSS template, single column, bundled fonts, PDF through WeasyPrint. Checks: at most two pages (bullets are dropped in a fixed priority order on overflow), Canadian format (no photo, age or marital status), and the extracted text layer matches the rendered content after whitespace normalisation.
- Cover letter and screening-answer bank (salary expectation, "why us", availability, work authorisation).
- English (Canada) by default; French (Canada) when the posting's language is French.

Acceptance: a CV built for a real posting in which every bullet traces to the bank, no evidence level rises, the PDF is two pages and its text layer matches.

### Phase 4 — Email reading

- `mail-worker` with a read-only IMAP connector (mailbox selected read-only, bodies fetched with peek so nothing is marked as seen) behind a provider interface. The stored credential is an app password, which by itself grants full mailbox access; the app states this to the user at connection time. Credentials are sealed with a libsodium sealed box (PyNaCl): `api` holds only the public key. The worker connects only to hosts on a hard-coded allowlist and only with values from the sealed blob; the password never enters a task payload. Confirm that Gmail still accepts app passwords; the fallback is the Gmail API with a read-only OAuth scope.
- Server-side filter by sender and date. The sender list is the ATS and scheduling domains shipped in the repo plus the company domains of the user's applications and watchlist, subdomains included. An opt-in, rules-only pass over headers surfaces "possibly related" senders for the user to approve; it involves no model.
- Structured classification: confirmation, rejection, interview invite, take-home, availability request, offer, other; company, role, dates, evidence quote, confidence.
- Linking to an application by sender domain, company and title similarity (`pg_trgm`). Ambiguous: the user picks. No match: propose a new card, which also covers applications made outside the app.
- Proposal inbox and a notification with a deep link, showing the message's DKIM/DMARC result. Approval writes the stage change with the email attached. An invite sets nothing by itself: the interview date is a field the user confirms.
- Backfill of 90 days on connection, idempotent on Message-ID.

Acceptance: `manage.py mail_replay` loads private fixtures into a clean tenant and yields the expected proposals, including two messages with the same subject and sender that differ only by the role named in the body; synthetic fixtures cover every class in the public tests.

### Phase 5 — Interview, salary and funnel

- Interview preparation: company brief from the posting, company pages and the user's notes; likely questions from the requirements; STAR stories linked to experience bullets; post-interview notes on the timeline.
- Salary intelligence: range observations by role family and level from every collected posting, percentiles and coverage; offer comparator (base, bonus, equity, benefits, RRSP match, vacation).
- Funnel analytics: response rate by source, track, CV version and posting type, and time to response, always with the sample size shown.

### Backlog

Networking CRM (contacts per company, with a connection feeding the score), skills gap map, browser extension, autofill, sources for non-tech careers, approve-from-Telegram buttons, routing-API commute times.

## 8. Patterns to port from the rental monitor

`rental-searcher/` is TypeScript and NestJS, so nothing is copied: each item below is re-implemented in Python together with its tests. Read the original before writing the port; the comments there record why each rule exists.

| What | Where | How it applies |
| --- | --- | --- |
| Polite HTTP | `src/seed/http.ts` | Identifiable User-Agent, 30 s timeout, three attempts on 5xx, none on 429/403. Port onto `httpx` and add query-string redaction in errors |
| Breaker and registry | `src/sources/rate-limiter.ts`, `src/sources/source.registry.ts` | Pause on 429/403, alert once per pause. Its state is in process memory there; here it lives in `source_state` |
| Source interface | `src/sources/source.interface.ts` | An ATS board is the "building" granularity (a container refreshed on a required interval); Adzuna is the paginated kind. Keep the unparsable-rows list and the delisting confirmation |
| Probe | `src/sources/probe/`, `src/probe-sources.ts` | A verdict per (source, vantage point); here a contract probe for documented APIs |
| Filters and scorer | `src/scoring/hard-filters.ts`, `src/scoring/scorer.ts`, `src/scoring/components/index.ts` | `pass`/`reject`/`review`, null-aware weighted sum, breakdown that adds up to the score, error on an unknown weight, linear decay |
| Audit tables | `src/db/schema/audit.ts`, `src/db/schema/matches.ts` | `rejection_log`, `needs_review`, stored breakdown, unique notification index |
| Profile schema | `src/profiles/profile.schema.ts`, `profiles.service.ts` | Validated JSON with a recursive rule type; invalid rows are logged and skipped. Pydantic replaces Zod |
| Transit and distance | `src/seed/transit.ts`, `src/geo/distance.ts`, `src/geo/geo.service.ts`, `src/geo/address.ts` | Overpass seed with its "fail loudly" guard (extend it to streetcar and bus stops, which it excludes on purpose), haversine and walking distance, in-memory index, address normalisation and geocoding |
| Notifications | `src/notifications/telegram.notifier.ts`, `notification.types.ts` | Claim before send, release if every recipient fails, one notifier interface for all channels. Quiet hours there use a fixed timezone (`pipeline.service.ts` L966-978) |
| Model pattern | `src/verification/listing-verifier.ts`, `apply-verdict.ts` | Fail-open, schema output, persisted verdict with evidence, replay without a new call, guards on what a verdict may change. It has no prompt caching |
| Rule extraction | `src/extraction/normalize.ts`, `rules.ts`, `src/listings/enrich.ts` | Rules return null when the text is silent; structured beats text; conflicts are flagged. Its HTML-to-text strips tags before decoding entities, which must be reversed for entity-escaped content |
| Reset discipline | `src/db/reset-operational.ts` | A reset that refuses any table it cannot classify |
| Operations | `src/health/`, `src/operations/`, `src/pipeline/watchdog.service.ts`, `src/run-cycle.ts` | `/health` says the process is up, `/operations` says work is getting done; dry-run and stored modes, funnel printout |
| Web | `web/src/api/client.ts`, `web/src/state/useFilters.ts` | Shape of the fetch wrapper and filters in the URL. Its client drops credentials on 403 as well as 401; here only 401 does. This is the one area that stays TypeScript |
| Acceptance | `src/verify.ts` | Checks against a real database, with a second profile inserted in a rolled-back transaction |

Not carried over: the single UI token (replaced by sessions and roles), the `setTimeout` scheduler (replaced by Celery beat), migrations at boot (replaced by the one-shot `migrate` service), and `sync-profile.ts` (it syncs a profile defined in code, which rule 3 forbids).

## 9. Verification

- Per commit, backend: `ruff check`, type check, `pytest`. Web: `pnpm typecheck`, `pnpm test`, `pnpm build`, and the generated API types are current.
- `manage.py verify`: acceptance checks against a real database, including a second profile with opposite rules inside a rolled-back transaction, and monotonic ladders for salary and commute.
- `manage.py probe`, `rank_stored`, `eval_ranking`, `mail_replay`: run locally or on the server, never in CI.
- Security: catalog meta-test, canary isolation suite, route classification test, demo role gets 403 on every unmarked route, hygiene script over the full git history.
- End to end per phase: the acceptance lists above, exercised on the deployed instance, with screenshots taken from the demo tenant.

## 10. Open items that do not block Phase 0

- Server architecture and memory (first task of Phase 0); application domain.
- Exact Django and CPython versions; whether Django's built-in task framework has matured enough to replace Celery (default: Celery).
- Keys: Anthropic and OpenAI (available), Adzuna (register), Telegram bot, SMTP sender, off-host backup target.
- App passwords for the mailboxes (Phase 4 only).
- Profile values for each user (salary floor, seniority, locations, home, commute thresholds): entered in the first-run wizard.
- Repository licence.
