"""scripts/hygiene.py: the guard that keeps personal data out of a public repository.

Each test builds a throwaway git repository. Nothing here touches the real one, and the denylist
entries are invented.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

# The script lives outside the backend package (the git hooks run it with no dependencies
# installed), so it is loaded by path.
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "hygiene.py"
spec = importlib.util.spec_from_file_location("hygiene", SCRIPT)
hygiene = importlib.util.module_from_spec(spec)
sys.modules["hygiene"] = hygiene  # dataclasses looks its module up by name
spec.loader.exec_module(hygiene)

NO_REPLY = "1234+someone@users.noreply.github.com"
DENYLIST = """
# comment
Zorblatt
José Example
cs:Acme
re:secret-\\d+
"""


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", NO_REPLY)
    git(tmp_path, "config", "commit.gpgsign", "false")
    git(tmp_path, "config", "core.hooksPath", "/dev/null")
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "denylist.txt").write_text(DENYLIST)
    (tmp_path / ".gitignore").write_text("private/\n")
    return tmp_path


def write(repo: Path, name: str, text: str = "hello\n") -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    git(repo, "add", "-f", name)


def run(repo: Path, *args: str) -> int:
    return hygiene.main([*args, "--repo", str(repo)])


# --- Matching


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("nothing to see", 0),
        ("mentions Zorblatt here", 1),
        ("case does not matter: ZORBLATT", 1),
        ("whole words only: Zorblatts, preZorblatt", 0),
        ("punctuation is a boundary: (zorblatt).", 1),
        ("accents are ignored: Jose Example", 1),
        ("and the other way round: José   Example", 1),
        ("cs entries need the exact case: Acme", 1),
        ("so the common word acme is fine", 0),
        ("regex: secret-123", 1),
        ("two at once: Zorblatt and Acme", 2),
    ],
)
def test_denylist_matching(repo, text, expected):
    patterns = hygiene.load_denylist(repo / "private" / "denylist.txt")
    assert hygiene.denylist_hits(text, patterns) == expected


@pytest.mark.parametrize(
    ("path", "guarded"),
    [
        ("notes.md", False),
        ("cv.pdf", True),
        ("saved/Reply.EML", True),
        ("docs/page.html", True),
        ("web/index.html", False),
        ("backend/apps/cv/templates/cv/base.html", False),
        ("backend/apps/cv/other/base.html", True),
    ],
)
def test_guarded_file_types(path, guarded):
    assert hygiene.is_guarded_type(path) is guarded


# --- staged


def test_a_clean_change_passes(repo, capsys):
    write(repo, "README.md")
    assert run(repo, "staged") == 0


def test_a_denylisted_term_in_content_is_refused_without_being_echoed(repo, capsys):
    write(repo, "notes.md", "applied to Zorblatt last week\n")
    assert run(repo, "staged") == 1
    output = capsys.readouterr()
    assert "notes.md" in output.err
    assert "zorblatt" not in (output.out + output.err).lower()


def test_a_denylisted_term_in_a_file_name_is_refused(repo):
    write(repo, "docs/zorblatt-notes.md")
    assert run(repo, "staged") == 1


def test_a_saved_document_is_refused_and_the_allowlist_is_honoured(repo):
    write(repo, "web/index.html", "<!doctype html>")
    assert run(repo, "staged") == 0
    write(repo, "docs/reply.html", "<p>thank you for your interest</p>")
    assert run(repo, "staged") == 1


def test_a_staged_file_under_private_is_refused(repo):
    write(repo, "private/context.md", "anything")
    assert run(repo, "staged") == 1


def test_only_the_staged_version_is_checked(repo):
    write(repo, "notes.md", "fine\n")
    (repo / "notes.md").write_text("Zorblatt, but not staged\n")
    assert run(repo, "staged") == 0


def test_a_personal_commit_email_is_refused(repo):
    git(repo, "config", "user.email", "someone@example.com")
    write(repo, "README.md")
    assert run(repo, "staged") == 1


# --- message


def test_commit_messages_are_checked_and_template_comments_ignored(repo, tmp_path):
    message = repo / "MSG"
    message.write_text("Add notes\n\n# Zorblatt appears only in a git comment line\n")
    assert run(repo, "message", str(message)) == 0
    message.write_text("Add notes after the Zorblatt rejection\n")
    assert run(repo, "message", str(message)) == 1


# --- history


def test_history_finds_what_a_later_commit_removed(repo):
    write(repo, "README.md")
    git(repo, "commit", "-qm", "Start")
    assert run(repo, "history") == 0

    write(repo, "notes.md", "Zorblatt\n")
    git(repo, "commit", "-qm", "Add notes")
    git(repo, "rm", "-q", "notes.md")
    git(repo, "commit", "-qm", "Remove notes")
    assert not (repo / "notes.md").exists()
    assert run(repo, "history") == 1


def test_history_checks_messages_file_types_and_identities(repo):
    write(repo, "README.md")
    git(repo, "commit", "-qm", "Start")

    git(repo, "commit", "-q", "--allow-empty", "-m", "Notes about Zorblatt")
    assert run(repo, "history") == 1
    git(repo, "reset", "-q", "--hard", "HEAD~1")
    assert run(repo, "history") == 0

    write(repo, "cv.pdf", "%PDF")
    git(repo, "commit", "-qm", "Add a file")
    assert run(repo, "history") == 1
    git(repo, "reset", "-q", "--hard", "HEAD~1")

    git(repo, "-c", "user.email=someone@example.com", "commit", "-q", "--allow-empty", "-m", "x")
    assert run(repo, "history") == 1


def test_history_covers_every_branch(repo):
    write(repo, "README.md")
    git(repo, "commit", "-qm", "Start")
    git(repo, "switch", "-qc", "side")
    write(repo, "notes.md", "Zorblatt\n")
    git(repo, "commit", "-qm", "Side work")
    git(repo, "switch", "-q", "main")
    assert run(repo, "history") == 1


# --- Without a denylist


def test_without_a_denylist_the_other_checks_still_run(repo, capsys):
    (repo / "private" / "denylist.txt").unlink()
    write(repo, "notes.md", "Zorblatt\n")
    assert run(repo, "staged") == 0
    assert "SKIPPED" in capsys.readouterr().err
    write(repo, "cv.pdf", "%PDF")
    assert run(repo, "staged") == 1


def test_require_denylist_turns_a_missing_file_into_a_failure(repo):
    (repo / "private" / "denylist.txt").unlink()
    write(repo, "README.md")
    assert run(repo, "staged", "--require-denylist") == 2
