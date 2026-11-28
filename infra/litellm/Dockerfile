# The model gateway: LiteLLM's image with this repository's configuration baked in, so the
# deployment needs no bind mount. The `-database` variant is the one that keeps virtual keys and
# budgets in Postgres. Pinned to a release at least two weeks old (ADR 0007).
FROM ghcr.io/berriai/litellm-database:v1.108.5
COPY config.yaml /app/config.yaml
CMD ["--config", "/app/config.yaml", "--port", "4000"]
