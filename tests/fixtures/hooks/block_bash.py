#!/usr/bin/env python3
"""Hook script for PreToolUse event that BLOCKS bash commands."""
import json
import sys


def main() -> None:
    payload = json.loads(sys.stdin.read())
    tool_name = payload.get("tool_name", "unknown")
    if tool_name == "bash":
        result = {
            "action": "block",
            "message": "[hook] Bash commands are blocked by hook",
        }
    else:
        result = {
            "action": "continue",
            "message": f"[hook] Tool allowed: {tool_name}",
        }
    sys.stdout.write(json.dumps(result))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
