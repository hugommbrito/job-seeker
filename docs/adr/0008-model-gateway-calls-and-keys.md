# 0008. How the worker calls the model gateway, and where its keys live

2026-11-24. Accepted for the code; **the deployment part is Proposed** until the first deploy
with keys. Refines the implementation plan, section 3.4, and section 3.2 for `litellm`.

## Context

Phase 1 adds the gateway and its first caller, the extraction of a pasted posting. Four things
were not settled by the plan, or turned out differently from it once the SDK was installed:

1. The plan says to use `client.messages.parse()`. The installed SDK (anthropic 2.8) validates
   every text block inside `parse()`, before the caller can read `stop_reason`. A cut-off answer
   therefore raises instead of coming back as "max_tokens", and the usage of that billed call
   is lost with the exception.
2. Coolify gives every variable of a compose application to all of its services (ADR 0004).
   A provider key or the gateway key set there would reach the api, which must hold none.
3. `llm_calls` has a user column, so it is either a tenant table or it breaks the catalog rule.
4. No key exists yet, so the spike in section 3.4 cannot run.

## Decision

- **Calls go through `messages.create()`** with `output_config.format` built by the SDK's
  public `anthropic.transform_schema(Model)`, the same transformation `parse()` uses. The stop
  reason is checked first (refusal, then max_tokens), and only then is the text validated with
  the same Pydantic model. Every outcome keeps its token counts. Adaptive thinking, an explicit
  effort per task (`LLM_TASKS`), no sampling parameters, no tools.
- **`llm_calls` is a tenant table.** Every Phase 1 call is made for one user. When Phase 2's
  shared extraction arrives, its call is recorded for the user whose ranking needed it, and the
  result is copied to the shared table. The stored answer is unique per (user, task, entity,
  prompt version, input hash); a concurrent second answer is kept as `duplicate`, for its cost.
- **Keys.** LiteLLM is its own Coolify resource (`infra/litellm/`), with its own variables: the
  Anthropic key, the master key and its database URL. The worker's budget-capped virtual key is
  a file in `/data/job-seeker/worker-secrets/`, mounted into the worker alone and read when a
  call is made; a missing file means "no gateway", not a crash. The api refuses to start when any
  model credential is in its environment (`llm.E001`, a warning in development).
- **Gateway settings.** Message logging to callbacks off, prompts not stored in spend logs,
  admin UI off, no public domain. Image `litellm-database` v1.108.5, with the configuration
  baked in so no bind mount is needed.
- **Refusal fallbacks are off** (`LLM_REFUSAL_FALLBACKS`) until the spike shows the gateway
  forwards them. A per-user cap of model calls per 24 hours (`LLM_DAILY_CALLS_PER_USER`, 100)
  sits under the gateway's own budget.
- **The spike is a command**, `manage.py llm_spike`, run on the worker once keys exist. Its
  logic is tested against a mocked transport; its verdict on the real gateway is still open.

## Consequences

- Until the spike passes, nothing is known about how LiteLLM 1.108 treats `output_config`,
  `cache_control` and adaptive thinking on its Anthropic endpoint, nor whether it accepts the
  API version SDK 2.x sends (`2026-10-21`). If any check fails, `LLM_GATEWAY_URL` moves to the
  pass-through route and the `LLM_MODEL_*` variables to model ids, with no code change.
- SDK 2.x sends the key as a bearer token; LiteLLM accepts that as it does `x-api-key`.
- One more file on the server to manage by hand, and one more Coolify resource.
