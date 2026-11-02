#!/usr/bin/env python3
"""Minimal Telegram Bot API helper (standard library only).

The token is read from the TELEGRAM_BOT_TOKEN environment variable, never from the command line,
so it doesn't end up in shell history or logs.

    python bot_api.py me                         # who is this bot?
    python bot_api.py updates [--offset N]       # recent updates: find chat ids here
    python bot_api.py send CHAT_ID "text" [--html] [--silent] [--yes]

`send` prints what it would send and exits unless --yes is given, so an agent has to show the user
the exact message and chat first.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.telegram.org/bot{token}/{method}"


def call(method: str, **params) -> dict:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("Set TELEGRAM_BOT_TOKEN first (from @BotFather).")
    data = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
    req = urllib.request.Request(API.format(token=token, method=method), data=data)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        body = json.load(e)
        # 403: the user never started the bot / blocked it. 429: wait parameters.retry_after.
        return body


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("me")
    up = sub.add_parser("updates")
    up.add_argument("--offset", type=int)
    sd = sub.add_parser("send")
    sd.add_argument("chat_id")
    sd.add_argument("text")
    sd.add_argument("--html", action="store_true", help="parse_mode=HTML")
    sd.add_argument("--silent", action="store_true", help="disable_notification")
    sd.add_argument("--yes", action="store_true", help="actually send")
    a = ap.parse_args()

    if a.cmd == "me":
        res = call("getMe")
    elif a.cmd == "updates":
        res = call("getUpdates", offset=a.offset, timeout=0)
        if res.get("ok"):
            # Summarise so chat ids are easy to spot; full JSON is still printed below.
            for u in res["result"]:
                m = u.get("message") or u.get("channel_post") or u.get("edited_message") or {}
                c = m.get("chat", {})
                print(f"update {u['update_id']}: chat_id={c.get('id')} type={c.get('type')} "
                      f"title={c.get('title') or c.get('username') or c.get('first_name')!r}", file=sys.stderr)
    else:
        if not a.yes:
            print(f"DRY RUN - would send to chat {a.chat_id}:\n---\n{a.text}\n---\n"
                  "Show this to the user; re-run with --yes once they confirm.")
            return 0
        res = call("sendMessage", chat_id=a.chat_id, text=a.text,
                   parse_mode="HTML" if a.html else None,
                   disable_notification="true" if a.silent else None)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
