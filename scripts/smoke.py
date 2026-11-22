#!/usr/bin/env python3
"""Acceptance check against a running instance: the app is up and people can sign in.

    scripts/smoke.py https://jobs.example.org --user first@example.org --user second@example.org

Passwords are prompted for, or read from SMOKE_PASSWORD_1, SMOKE_PASSWORD_2, ... in the order
the users are given. They are never taken as arguments.

It behaves like a browser: it gets the CSRF cookie, signs in, reads the session and the profile,
signs out, and checks the cookie flags and security headers on the way. Run it by hand after a
deploy; it is not part of CI, because CI holds no credentials.

Standard library only.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from http.cookies import SimpleCookie


class Browser:
    """Just enough of a browser: a cookie jar that also sends Secure cookies to plain HTTP,
    so the script can be pointed at a local server that is configured like production."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.cookies: dict[str, str] = {}
        self.cookie_attributes: dict[str, dict[str, str]] = {}

    def request(
        self, method: str, path: str, body: dict | None = None, csrf: bool = True
    ) -> tuple[int, dict[str, str], bytes]:
        headers = {"Accept": "application/json, text/html", "User-Agent": "job-seeker-smoke/1"}
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if method != "GET":
            # What a browser sends on a same-origin write; the server's CSRF check requires it.
            headers["Origin"] = self.base_url
            headers["Referer"] = self.base_url + "/"
            if csrf and "csrftoken" in self.cookies:
                headers["X-CSRFToken"] = self.cookies["csrftoken"]
        request = urllib.request.Request(  # noqa: S310 - the URL is the operator's own instance
            self.base_url + path, data=data, method=method, headers=headers
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
                status, raw_headers, content = response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            status, raw_headers, content = error.code, error.headers, error.read()
        for header in raw_headers.get_all("Set-Cookie") or []:
            cookie = SimpleCookie()
            cookie.load(header)
            for name, morsel in cookie.items():
                if morsel.value:
                    self.cookies[name] = morsel.value
                else:
                    self.cookies.pop(name, None)
                self.cookie_attributes[name] = {
                    key: str(morsel[key]) for key in ("httponly", "secure", "samesite")
                }
        return status, {k.lower(): v for k, v in raw_headers.items()}, content


class Report:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, ok: bool, what: str) -> bool:
        print(f"  {'ok  ' if ok else 'FAIL'} {what}")
        if not ok:
            self.failures += 1
        return ok


def check_public(base_url: str, report: Report) -> None:
    print("Public surface")
    browser = Browser(base_url)
    secure = base_url.startswith("https://")

    status, _, content = browser.request("GET", "/health")
    report.check(status == 200 and json.loads(content or b"{}") == {"status": "ok"}, "/health")

    status, headers, content = browser.request("GET", "/")
    report.check(status == 200 and b'<div id="root">' in content, "/ serves the web client")
    policy = headers.get("content-security-policy", "")
    report.check("script-src 'self'" in policy, "Content-Security-Policy restricts scripts")
    report.check(headers.get("x-frame-options") == "DENY", "X-Frame-Options is DENY")
    if secure:
        report.check("strict-transport-security" in headers, "HSTS header is present")

    status, _, _ = browser.request("GET", "/api/auth/me")
    report.check(status == 401, "/api/auth/me requires a session")

    status, _, _ = browser.request("GET", "/api/docs")
    report.check(status == 404, "the interactive API docs are not exposed")

    browser.request("GET", "/api/auth/csrf")
    status, _, _ = browser.request(
        "POST", "/api/auth/login", {"email": "nobody@example.invalid", "password": "x"}, csrf=False
    )
    report.check(status == 403, "sign-in without the CSRF token is refused")


def check_user(base_url: str, email: str, password: str, report: Report) -> None:
    # The position, not the address, is printed: this output gets pasted into deploy notes.
    browser = Browser(base_url)
    secure = base_url.startswith("https://")

    status, _, _ = browser.request("GET", "/api/auth/csrf")
    report.check(status == 204 and "csrftoken" in browser.cookies, "CSRF cookie issued")

    status, _, content = browser.request(
        "POST", "/api/auth/login", {"email": email, "password": password}
    )
    if not report.check(status == 200, f"sign-in accepted (HTTP {status})"):
        return
    role = json.loads(content).get("role")

    flags = browser.cookie_attributes.get("sessionid", {})
    report.check(bool(flags.get("httponly")), "session cookie is HttpOnly")
    report.check(flags.get("samesite") == "Lax", "session cookie is SameSite=Lax")
    if secure:
        report.check(bool(flags.get("secure")), "session cookie is Secure")

    status, _, content = browser.request("GET", "/api/auth/me")
    same = status == 200 and json.loads(content).get("email") == email.strip().lower()
    report.check(same, f"session belongs to this user (role: {role})")

    status, _, content = browser.request("GET", "/api/profile")
    report.check(status == 200 and "timezone" in json.loads(content or b"{}"), "profile loads")

    status, _, _ = browser.request("POST", "/api/auth/logout")
    report.check(status == 204, "sign-out accepted")
    status, _, _ = browser.request("GET", "/api/auth/me")
    report.check(status == 401, "session is gone after sign-out")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test a running job-seeker instance.")
    parser.add_argument("base_url")
    parser.add_argument("--user", action="append", default=[], metavar="EMAIL")
    args = parser.parse_args()

    report = Report()
    check_public(args.base_url, report)
    for index, email in enumerate(args.user, start=1):
        print(f"User {index}")
        password = os.environ.get(f"SMOKE_PASSWORD_{index}") or getpass.getpass(
            f"Password for user {index}: "
        )
        check_user(args.base_url, email, password, report)

    if report.failures:
        print(f"\n{report.failures} check(s) failed")
        return 1
    print(f"\nAll checks passed ({len(args.user)} user(s) signed in)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
