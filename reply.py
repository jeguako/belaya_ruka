from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

BASE_DIR = Path(__file__).resolve().parent
PENDING = BASE_DIR / "outbox" / "pending"


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit('Usage: python reply.py "message text" [chat_id]')

    text = sys.argv[1].strip()
    chat_id = sys.argv[2].strip() if len(sys.argv) > 2 else ""
    if not text:
        raise SystemExit("Message text is empty")

    PENDING.mkdir(parents=True, exist_ok=True)
    task_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    payload = {
        "task_id": task_id,
        "text": text,
    }
    if chat_id.isdigit():
        payload["chat_id"] = int(chat_id)

    path = PENDING / f"{task_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Queued reply: {path}")


if __name__ == "__main__":
    main()
