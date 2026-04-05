#!/usr/bin/env python3
"""Hook script for PostToolUse event: logs tool results."""
import json
import sys


def main() -> None:
    payload = json.loads(sys.stdin.read())
    tool_name = payload.get("tool_name", "unknown")
    is_error = payload.get("is_error", False)
    result = {
        "action": "continue",
        "message": f"[hook] PostToolUse logged: {tool_name} (error={is_error})",
    }
    sys.stdout.write(json.dumps(result))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
