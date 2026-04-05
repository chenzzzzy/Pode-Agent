#!/usr/bin/env python3
"""Hook script for UserPromptSubmit event: allows the prompt."""
import json
import sys


def main() -> None:
    payload = json.loads(sys.stdin.read())
    prompt = payload.get("prompt", "")
    result = {
        "action": "continue",
        "message": f"[hook] Prompt received ({len(prompt)} chars)",
    }
    sys.stdout.write(json.dumps(result))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
