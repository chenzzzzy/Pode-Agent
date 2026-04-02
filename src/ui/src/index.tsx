/**
 * Pode-Agent UI — Ink entry point.
 *
 * Bootstraps the JSON-RPC client, connects to the Python backend
 * via stdio, and renders the REPL screen.
 */

import React from "react"
import { render, Box, Text } from "ink"
import { JsonRpcPeer } from "./rpc/client.js"
import { StdioTransport } from "./rpc/transport.js"
import { REPL } from "./screens/REPL.js"
import { getTheme } from "./theme.js"

// --- JSON-RPC setup ---

const peer = new JsonRpcPeer()
const transport = new StdioTransport(peer, {
  writeLine: (line: string) => {
    process.stdout.write(line + "\n")
  },
})

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
