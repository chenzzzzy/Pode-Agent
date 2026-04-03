/**
 * TCP socket transport for JSON-RPC.
 *
 * Connects to the Python backend via TCP socket (port from PODE_RPC_PORT env).
 * This allows the Bun process to keep stdin/stdout connected to the TTY
 * for Ink's user input handling (which requires raw mode).
 *
 * Architecture:
 *
 *   Python (parent)  ─── TCP socket (JSON-RPC) ───  Bun (child, Ink UI)
 *   UIBridge listens on a port, Bun connects to it
 *   Bun's stdin/stdout remain connected to TTY for user input
 */

import * as net from "node:net"
import { JsonRpcPeer } from "./client"

export type TransportOptions = {
  port: number
  host?: string
}

export class SocketTransport {
  private socket: net.Socket | null = null
  private readonly pending = new Set<Promise<void>>()
  private readonly port: number
  private readonly host: string

  constructor(
    private readonly peer: JsonRpcPeer,
    opts: TransportOptions,
  ) {
    this.port = opts.port
    this.host = opts.host ?? "127.0.0.1"
  }

  start(): void {
    if (this.socket) return

    // Set up the send function
    this.peer.setSend((line: string) => {
      this.socket?.write(line + "\n")
    })

    // Connect to Python backend via TCP
    this.socket = net.createConnection(
      { port: this.port, host: this.host },
      () => {
        // Connection established
      },
    )

    this.socket.on("data", (data: Buffer) => {
      const lines = data.toString("utf-8").split("\n")
      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed) continue

        try {
          const payload = JSON.parse(trimmed)
          const p = this.peer.handleIncoming(payload).catch(() => {
            // Swallow handler errors
          })
          this.pending.add(p)
          void p.finally(() => this.pending.delete(p))
        } catch {
          this.socket?.write(
            JSON.stringify({
              jsonrpc: "2.0",
              id: null,
              error: { code: -32700, message: "Parse error" },
            }) + "\n",
          )
        }
      }
    })

    this.socket.on("close", () => {
      void (async () => {
        const pending = Array.from(this.pending)
        if (pending.length > 0) {
          await Promise.allSettled(pending)
        }
        process.exit(0)
      })()
    })

    this.socket.on("error", (err) => {
      console.error("RPC socket error:", err.message)
      process.exit(1)
    })
  }

  stop(): void {
    this.socket?.destroy()
    this.socket = null
  }
}

// Alias for backwards compatibility
export const StdioTransport = SocketTransport
