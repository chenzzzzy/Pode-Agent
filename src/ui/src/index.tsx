/**
 * Pode-Agent UI — Ink entry point.
 *
 * Bootstraps the JSON-RPC client, connects to the Python backend
 * via TCP socket (port from PODE_RPC_PORT env), and renders the REPL screen.
 *
 * Architecture:
 *
 *   Python (parent)  ─── TCP socket (JSON-RPC) ───  Bun (child, Ink UI)
 *   UIBridge listens on a port, Bun connects to it
 *   Bun's stdin/stdout remain connected to TTY for user input
 */

import React from "react"
import { render, Box, Text } from "ink"
import { JsonRpcPeer } from "./rpc/client.js"
import { SocketTransport } from "./rpc/transport.js"
import { REPL } from "./screens/REPL.js"
import { getTheme } from "./theme.js"

// --- Check TTY support before rendering ---
if (!process.stdin.isTTY) {
  console.error(`
Error: Pode-Agent requires an interactive terminal (TTY).

If running from a script or pipe, use print mode instead:
  pode "your prompt here"

Or run directly in a terminal:
  uv run pode
`)
  process.exit(1)
}

// --- JSON-RPC setup ---

const peer = new JsonRpcPeer()

// Get RPC port from environment
const port = parseInt(process.env.PODE_RPC_PORT || "0", 10)
if (!port) {
  console.error("Error: PODE_RPC_PORT environment variable not set")
  process.exit(1)
}

// Create socket transport
const transport = new SocketTransport(peer, { port })

// --- App ---

function App() {
  const theme = getTheme()

  return (
    <REPL
      peer={peer}
      theme={theme}
    />
  )
}

// --- Bootstrap ---

render(<App />, {
  exitOnCtrlC: false,
})

transport.start()
