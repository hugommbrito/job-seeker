#!/bin/sh
# One-time setup after cloning. Safe to run again.
set -e
cd "$(git rev-parse --show-toplevel)"

# Hooks live in the repository so every clone gets the same checks.
git config core.hooksPath .githooks
echo "git hooks: enabled (.githooks)"

if [ ! -f private/denylist.txt ]; then
  echo "note: private/denylist.txt does not exist, so the denylist check is skipped."
  echo "      Create it (one term per line) if you keep personal data next to this checkout."
fi

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "note: gitleaks is not installed; the secret scan then runs only in CI."
fi

email="$(git config user.email || true)"
case "$email" in
  *@users.noreply.github.com) ;;
  *)
    echo "note: git user.email for this repository is not a GitHub no-reply address."
    echo "      The pre-commit hook refuses commits until it is, for example:"
    echo "      git config user.email '<id>+<login>@users.noreply.github.com'"
    ;;
esac
