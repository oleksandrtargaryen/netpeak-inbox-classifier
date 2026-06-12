"""Optional: send the digest to Telegram via the Bot API.

Only runs if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set. Uses urllib so we
don't pull in an extra dependency just for one POST.
"""

import json
import os
import urllib.request
from collections import Counter

from ..models import ClassifiedRequest


def _digest_text(results: list[ClassifiedRequest]) -> str:
    total = len(results)
    by_cat = Counter(r.category.value for r in results)
    by_prio = Counter(r.priority.value for r in results)
    need = [r for r in results if r.needs_clarification]

    lines = [f"Inbox digest: {total} requests", ""]
    lines.append("By category:")
    for k, n in by_cat.most_common():
        lines.append(f"  {k}: {n}")
    lines.append("")
    lines.append("By priority:")
    for p in ("high", "medium", "low"):
        if by_prio[p]:
            lines.append(f"  {p}: {by_prio[p]}")
    lines.append("")
    lines.append(f"Need clarification: {len(need)} ({', '.join(r.id for r in need) or '-'})")
    return "\n".join(lines)


def send_digest(results: list[ClassifiedRequest]) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[telegram] skipped: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": _digest_text(results)}).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        print("[telegram] digest sent")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[telegram] failed to send: {e}")
        return False
