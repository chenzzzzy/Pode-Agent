#!/usr/bin/env python3
"""Hook script for PreToolUse event: logs tool calls and allows them."""
import json
import sys


def main() -> None:
    payload = json.loads(sys.stdin.read())
    tool_name = payload.get("tool_name", "unknown")
    result = {
        "action": "continue",
        "message": f"[hook] PreToolUse allowed: {tool_name}",
    }
    sys.stdout.write(json.dumps(result))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
