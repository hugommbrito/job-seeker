#!/usr/bin/env python3
"""Keep personal data and stray documents out of the repository.

This repository is public, and the application handles CVs and application emails. Three checks
keep the two apart:

* denylist   terms listed in ``private/denylist.txt`` (names, employers, companies applied to)
             must not appear in file contents, file names or commit messages;
* file types ``.pdf``, ``.eml`` and ``.html`` files are refused outside a short allowlist, because
             that is what a saved CV or email looks like;
* identity   author and committer emails must be no-reply addresses, so a personal address never
             ends up in commit metadata.

Modes:

    hygiene.py staged              the index, run by the pre-commit hook
    hygiene.py message <file>      a commit message, run by the commit-msg hook
    hygiene.py history             every commit reachable from any ref (acceptance and CI)

The denylist is itself private, so it exists only on the owner's machine. Without it the denylist
check is skipped with a warning; ``--require-denylist`` turns that into a failure, which is what
the acceptance run uses so it cannot pass by accident. CI runs ``history`` without the denylist
and still enforces file types and identities.

Standard library only: the hooks must work before any dependency is installed.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DENYLIST_PATH = REPO_ROOT / "private" / "denylist.txt"

# Document types that saved CVs and emails arrive in.
GUARDED_SUFFIXES = (".pdf", ".eml", ".html", ".htm")

# The only places a guarded file type is legitimate. Patterns use fnmatch, where ``*`` also
# crosses directory separators.
FILETYPE_ALLOWLIST = (
    "web/index.html",
    "backend/apps/*/templates/*.html",
)

# Commit identities allowed in history: GitHub's per-user no-reply addresses, and the address
# GitHub itself commits with for changes made in its web UI.
ALLOWED_EMAIL = re.compile(r"^(?:[\w.+-]+@users\.noreply\.github\.com|noreply@github\.com)$")

# Paths never scanned for denylist terms: the denylist's own directory is ignored by git, so
# nothing here is reachable; kept as a guard in case that changes.
SKIPPED_PREFIXES = ("private/",)


@dataclass(frozen=True)
class Finding:
    where: str
    what: str

    def __str__(self) -> str:
        return f"  {self.where}: {self.what}"


def fold(text: str) -> str:
    """Remove accents so an entry matches with or without them."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def compile_entry(line: str) -> re.Pattern[str]:
    """Turn one denylist line into a pattern applied to accent-folded text."""
    if line.startswith("re:"):
        return re.compile(fold(line[3:]), re.IGNORECASE)
    case_sensitive = line.startswith("cs:")
    literal = fold(line[3:] if case_sensitive else line).strip()
    # Whole word: a short name must not fire inside an unrelated longer token.
    body = r"\s+".join(re.escape(part) for part in literal.split())
    pattern = rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])"
    return re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)


def load_denylist(path: Path) -> list[re.Pattern[str]] | None:
    """Return the compiled denylist, or None when the file does not exist."""
    if not path.is_file():
        return None
    patterns = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            patterns.append(compile_entry(line))
    return patterns


def denylist_hits(text: str, patterns: list[re.Pattern[str]]) -> int:
    """Count matching entries. The matched text is never echoed: output may be pasted publicly."""
    folded = fold(text)
    return sum(1 for pattern in patterns if pattern.search(folded))


def is_guarded_type(path: str) -> bool:
    lowered = path.lower()
    if not lowered.endswith(GUARDED_SUFFIXES):
        return False
    return not any(fnmatch.fnmatchcase(path, allowed) for allowed in FILETYPE_ALLOWLIST)


def git(*args: str, repo: Path, text: bool = True) -> str | bytes:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)
    return result.stdout.decode("utf-8", errors="replace") if text else result.stdout


def decode(blob: bytes) -> str:
    return blob.decode("utf-8", errors="replace")


def check_path(path: str, where: str, patterns: list[re.Pattern[str]] | None) -> list[Finding]:
    findings = []
    if is_guarded_type(path):
        findings.append(
            Finding(where, "guarded file type (.pdf/.eml/.html) outside the allowlist")
        )
    if patterns and denylist_hits(path, patterns):
        findings.append(Finding(where, "file name matches a denylist entry"))
    return findings


def check_content(text: str, where: str, patterns: list[re.Pattern[str]] | None) -> list[Finding]:
    if not patterns:
        return []
    hits = denylist_hits(text, patterns)
    if hits:
        return [Finding(where, f"content matches {hits} denylist entr{'y' if hits == 1 else 'ies'}")]
    return []


def check_identity(email: str, where: str) -> list[Finding]:
    if ALLOWED_EMAIL.match(email):
        return []
    # The address is not echoed for the same reason matches are not.
    return [Finding(where, "email is not a GitHub no-reply address")]


def run_staged(repo: Path, patterns: list[re.Pattern[str]] | None) -> list[Finding]:
    findings: list[Finding] = []
    listing = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z", repo=repo)
    assert isinstance(listing, str)
    for path in filter(None, listing.split("\0")):
        if path.startswith(SKIPPED_PREFIXES):
            findings.append(Finding(path, "file under private/ is staged; it must stay ignored"))
            continue
        findings += check_path(path, path, patterns)
        blob = git("show", f":{path}", repo=repo, text=False)
        assert isinstance(blob, bytes)
        findings += check_content(decode(blob), path, patterns)
    for var in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
        ident = git("var", var, repo=repo)
        assert isinstance(ident, str)
        match = re.search(r"<([^>]*)>", ident)
        findings += check_identity(match.group(1) if match else "", var.lower())
    return findings


def run_message(message_file: Path, patterns: list[re.Pattern[str]] | None) -> list[Finding]:
    text = message_file.read_text(encoding="utf-8", errors="replace")
    # Lines starting with '#' are git's own template comments and are not part of the message.
    body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    return check_content(body, "commit message", patterns)


def run_history(repo: Path, patterns: list[re.Pattern[str]] | None) -> list[Finding]:
    findings: list[Finding] = []

    log = git("log", "--all", "--format=%H%x1f%ae%x1f%ce%x1f%B%x1e", repo=repo)
    assert isinstance(log, str)
    for record in filter(None, (chunk.strip("\n") for chunk in log.split("\x1e"))):
        sha, author_email, committer_email, message = record.split("\x1f", 3)
        short = sha[:10]
        findings += check_identity(author_email, f"{short} author")
        findings += check_identity(committer_email, f"{short} committer")
        findings += check_content(message, f"{short} message", patterns)

    # Every blob ever committed, with one of the paths it was committed under.
    objects = git("rev-list", "--all", "--objects", repo=repo)
    assert isinstance(objects, str)
    seen: set[str] = set()
    for line in objects.splitlines():
        sha, _, path = line.partition(" ")
        if not path or sha in seen:
            continue
        seen.add(sha)
        kind = git("cat-file", "-t", sha, repo=repo)
        assert isinstance(kind, str)
        if kind.strip() != "blob":
            continue
        where = f"{path} ({sha[:10]})"
        findings += check_path(path, where, patterns)
        if patterns:
            blob = git("cat-file", "blob", sha, repo=repo, text=False)
            assert isinstance(blob, bytes)
            findings += check_content(decode(blob), where, patterns)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("mode", choices=("staged", "message", "history"))
    parser.add_argument("message_file", nargs="?", type=Path)
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--denylist", type=Path, default=None)
    parser.add_argument(
        "--require-denylist",
        action="store_true",
        help="fail when the denylist file is missing instead of skipping that check",
    )
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    denylist_path = args.denylist or (repo / "private" / "denylist.txt")
    patterns = load_denylist(denylist_path)
    if patterns is None:
        if args.require_denylist:
            print(f"hygiene: denylist not found at {denylist_path}", file=sys.stderr)
            return 2
        print(
            "hygiene: no private/denylist.txt, so the denylist check is SKIPPED "
            "(file types and identities are still checked)",
            file=sys.stderr,
        )

    if args.mode == "staged":
        findings = run_staged(repo, patterns)
    elif args.mode == "message":
        if args.message_file is None:
            parser.error("message mode needs the path of the commit message file")
        findings = run_message(args.message_file, patterns)
    else:
        findings = run_history(repo, patterns)

    if findings:
        print(f"hygiene ({args.mode}): {len(findings)} problem(s)", file=sys.stderr)
        for finding in findings:
            print(finding, file=sys.stderr)
        print(
            "Personal data and saved documents belong in private/. See CLAUDE.md, rule 1.",
            file=sys.stderr,
        )
        return 1
    print(f"hygiene ({args.mode}): ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
