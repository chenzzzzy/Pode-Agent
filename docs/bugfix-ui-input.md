# Bug Fix Record: UI Input Not Working

> Date: 2026-04-03
> Status: Resolved
> Severity: Critical

## Problem Description

When running `uv run pode`, the application had multiple issues:

1. **Initial symptom**: Process hung at "UI bridge started, waiting for JSON-RPC" with increasing CPU and memory usage
2. **After initial fix**: Logo displayed correctly but terminal input not working - could type but couldn't delete or modify text
3. **After TCP fix**: `AttributeError: 'socket' object has no attribute 'write'` when sending messages

## Root Cause Analysis

### Issue 1: Stderr Pipe Deadlock

**Location**: `pode_agent/entrypoints/cli.py:176-182`

**Problem**: Bun subprocess was spawned with `stderr=PIPE` but stderr was never drained.

```python
# Original problematic code
proc = await asyncio.create_subprocess_exec(
    bun_path, "run", str(ui_entry),
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,  # <-- Never drained!
    cwd=str(ui_dir),
)
```

**Mechanism**:
1. Bun outputs warnings/debug info to stderr (normal behavior)
2. OS pipe buffer (4-64KB on Windows) fills up
3. Bun blocks on `write(stderr)` when buffer is full
4. Entire process hangs with increasing memory

**Fix**: Changed `stderr=PIPE` to `stderr=None` (inherit parent stderr)

### Issue 2: Ink Requires TTY for Raw Mode

**Location**: `pode_agent/entrypoints/cli.py`, `src/ui/src/rpc/transport.ts`, `src/ui/src/index.tsx`

**Problem**: When Python spawns Bun with piped stdin (`stdin=PIPE`), the Bun process's stdin is a pipe, not a TTY. Ink's `useInput` hook requires raw mode which only works on real terminals.

**Error message**:
```
ERROR Raw mode is not supported on the current process.stdin, which Ink uses
     as input stream by default.
```

**Original Architecture**:
```
Python (parent)  ─── pipe stdin/stdout ───  Bun (child, Ink UI)
                   (JSON-RPC)
```

Problem: Bun's stdin is a pipe, not TTY → Ink can't use raw mode

**Fixed Architecture**:
```
Python (parent)  ─── TCP socket (127.0.0.1:random_port) ───  Bun (child)
                   (JSON-RPC)

Bun's stdin/stdout remain connected to TTY for user input
```

**Implementation**:
1. Python starts TCP server on random port
2. Passes port number via `PODE_RPC_PORT` environment variable
3. Bun inherits parent's TTY for stdin/stdout
4. Bun connects to Python via TCP socket for JSON-RPC

### Issue 3: Multiple `useInput` Hooks Conflict

**Location**: `src/ui/src/screens/REPL.tsx`, `src/ui/src/components/PromptInput.tsx`, `src/ui/src/hooks/useExitOnCtrlCD.ts`, `src/ui/src/hooks/useCancelRequest.ts`

**Problem**: Multiple components used `useInput` simultaneously:
- `REPL.tsx` via `useExitOnCtrlCD`
- `REPL.tsx` via `useCancelRequest`
- `PromptInput.tsx` directly

This could cause input events to be processed incorrectly or multiple times.

**Fix**: Consolidated all input handling into a single `useInput` in `REPL.tsx`:
1. `PromptInput` now uses `forwardRef` to expose `handleInput` method
2. `REPL` uses a single `useInput` hook
3. All input events are delegated to `PromptInput` via ref

### Issue 4: State Reset on Re-render

**Location**: `src/ui/src/hooks/useExitOnCtrlCD.ts:10`

**Problem**: Used `let lastPress = 0` instead of `useRef`, causing the timestamp to reset on component re-renders.

```typescript
// Original - resets on every render
export function useExitOnCtrlCD() {
  let lastPress = 0  // <-- Problem
  ...
}

// Fixed - persists across renders
export function useExitOnCtrlCD() {
  const lastPressRef = useRef(0)
  ...
}
```

### Issue 5: StreamWriter Created with Socket Instead of Transport

**Location**: `pode_agent/entrypoints/cli.py:210-214`

**Problem**: `StreamWriter` was created with the raw socket object instead of the transport object.

```python
# Original - WRONG
writer = asyncio.StreamWriter(conn, protocol, reader, loop)
#                                  ^^^^ socket, not transport!
```

**Error**:
```
AttributeError: 'socket' object has no attribute 'write'
```

**Mechanism**:
- `StreamWriter.write()` calls `self._transport.write()`
- When `_transport` is a socket instead of a transport, it fails
- Sockets have `send()`, not `write()`

**Fix**: Use `connect_accepted_socket()` which returns `(transport, protocol)`, then create `StreamWriter` with the transport:

```python
# Fixed - CORRECT
reader = asyncio.StreamReader()
protocol = asyncio.StreamReaderProtocol(reader)
transport, _ = await loop.connect_accepted_socket(lambda: protocol, conn)
writer = asyncio.StreamWriter(transport, protocol, reader, loop)
#                               ^^^^^^^^^ transport, not socket!
```

## Files Modified

### Python Backend

| File | Change |
|------|--------|
| `pode_agent/entrypoints/cli.py` | TCP server for JSON-RPC, proper `StreamWriter` creation with transport |

### TypeScript Frontend

| File | Change |
|------|--------|
| `src/ui/src/rpc/transport.ts` | `SocketTransport` class for TCP communication |
| `src/ui/src/index.tsx` | TTY check + socket connection |
| `src/ui/src/screens/REPL.tsx` | Single `useInput` with ref delegation |
| `src/ui/src/components/PromptInput.tsx` | `forwardRef` + `handleInput` method |
| `src/ui/src/hooks/useExitOnCtrlCD.ts` | `useRef` instead of `let` variable |

## Lessons Learned

1. **Pipe buffers are finite**: When spawning subprocesses with piped streams, always drain or inherit all streams (stdin, stdout, stderr)

2. **Ink requires TTY**: Terminal UI frameworks like Ink need real TTY for raw mode. Use alternative communication channels (TCP, Unix sockets) for IPC

3. **Single source of truth for input**: Multiple `useInput` hooks can conflict. Use a single input handler and delegate via refs

4. **React state vs refs**: Use `useRef` for values that shouldn't trigger re-renders and need to persist across renders

5. **asyncio StreamWriter requires Transport**: When creating a `StreamWriter`, the first argument must be a `Transport` object (from `connect_accepted_socket` or similar), NOT a raw socket

## Testing

Run directly in a terminal (not through `timeout` or scripts which pipe stdin):

```bash
uv run pode
```

Expected behavior:
- Logo displays correctly
- Can type text in the prompt
- Backspace deletes characters
- Arrow keys move cursor
- Ctrl+A/E move to start/end
- Double Ctrl+C exits
- Messages are sent and received correctly

## Related Issues

- [Ink #isRawModeSupported](https://github.com/vadimdemedes/ink/#israwmodesupported)
- [asyncio.StreamWriter documentation](https://docs.python.org/3/library/asyncio-stream.html#streamwriter)
- Similar pattern used by other terminal UI tools: use TCP/socket for IPC, keep TTY for user input