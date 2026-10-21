#!/usr/bin/env python3
"""Smoke-test critical user flows against running API."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"


def req(method: str, path: str, body: dict | None = None) -> tuple[int, dict | list | str]:
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
    request = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def main() -> int:
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        if ok:
            print(f"OK  {name}")
        else:
            msg = f"FAIL {name}" + (f": {detail}" if detail else "")
            print(msg)
            failures.append(msg)

    code, health = req("GET", "/healthz")
    check("healthz", code == 200 and health == {"status": "ok"}, str(health))

    code, sessions = req("GET", "/api/v1/chat/sessions?page=1&page_size=5")
    check("list sessions", code == 200 and isinstance(sessions, dict) and "items" in sessions, f"{code} {sessions}")

    code, created = req("POST", "/api/v1/chat/sessions", {})
    sid = created.get("session_id") if isinstance(created, dict) else None
    check("create session null title", code == 201 and sid, f"{code} {created}")

    if sid:
        code, patched = req("PATCH", f"/api/v1/chat/sessions/{sid}", {"title": "E2E test chat", "pinned": True})
        check("patch rename+pin", code == 200 and patched.get("pinned") is True, f"{code} {patched}")

        code, ask = req(
            "POST",
            f"/api/v1/chat/{sid}/ask",
            {"question": "สายพาน MC-001 มีเสียงดังไหม", "filter": {"factory_id": "F-01"}},
        )
        check("ask question", code == 200 and isinstance(ask, dict) and ask.get("answer"), f"{code} {str(ask)[:200]}")

        code, listed = req("GET", "/api/v1/chat/sessions?page=1&page_size=50")
        row = next((i for i in listed.get("items", []) if i.get("session_id") == sid), None) if isinstance(listed, dict) else None
        title = row.get("title") if row else None
        check("auto-title after ask", code == 200 and title and title not in (None, "New chat", "แชทใหม่"), f"title={title!r}")

        code, _ = req("DELETE", f"/api/v1/chat/sessions/{sid}")
        check("delete session", code == 204, str(code))

    code, insights = req("GET", "/api/v1/insights/problem-pulse?factory_id=F-01&days=7")
    check("insights pulse", code == 200 and isinstance(insights, list), f"{code} {str(insights)[:120]}")

    code, alerts = req("GET", "/api/v1/alerts?page=1&page_size=10")
    check("list alerts", code == 200 and isinstance(alerts, dict), f"{code} {str(alerts)[:120]}")

    code, docs = req("GET", "/api/v1/documents?limit=5")
    check("list documents", code == 200, f"{code} {str(docs)[:120]}")

    if failures:
        print("\n--- FAILURES ---")
        for f in failures:
            print(f)
        return 1
    print("\nAll smoke flows passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
