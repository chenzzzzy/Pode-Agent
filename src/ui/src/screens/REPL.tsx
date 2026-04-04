/**
 * REPL Screen — main interactive REPL for Pode-Agent.
 *
 * Ported from Kode-Agent src/ui/screens/REPL.tsx (779 lines).
 * Adapted to use JSON-RPC instead of direct query() calls.
 *
 * Key architectural differences from Kode-Agent:
 * - Messages come via JSON-RPC notifications rather than async generator
 * - Permission flow uses resolve_permission RPC request instead of Promise callback
 * - Message normalization is simpler (flat typed messages vs API content blocks)
 */

import React, { useCallback, useEffect, useMemo, useState } from "react"
import { Box, Static, Text, useApp, useInput } from "ink"
import type { JsonRpcPeer } from "../rpc/client.js"
import type { Theme, Message, PermissionDecision, UsageStats } from "../types.js"
import type { PlanState } from "../hooks/useSession.js"
import { useSession } from "../hooks/useSession.js"
import { Logo } from "../components/Logo.js"
import { Spinner } from "../components/Spinner.js"
import { PromptInput } from "../components/PromptInput.js"
import { Message as MessageComponent } from "../components/Message.js"
import { PermissionRequest } from "../components/permissions/PermissionRequest.js"
import {
  normalizeMessages,
  reorderMessages,
  getStaticPrefixLength,
} from "../utils/messages.js"

export interface REPLProps {
  peer: JsonRpcPeer
  theme: Theme
  initialPrompt?: string
  verbose?: boolean
  safeMode?: boolean
  onNavigate?: (screen: string) => void
}

/** Sentinel item for the logo in the Static list. */
const LOGO_ITEM = { id: "__logo__", _isLogo: true as const }
type LogoItem = typeof LOGO_ITEM
type StaticItem = Message | LogoItem
function isLogoItem(item: StaticItem): item is LogoItem {
  return "_isLogo" in item
}

/** Built-in slash command help text. */
const HELP_TEXT =
  "Available commands:\n" +
  "  /help   – Show this help message\n" +
  "  /clear  – Clear the conversation\n" +
  "  /model  – Show the current model\n" +
  "  /doctor – Run diagnostics"

export function REPL({ peer, theme, initialPrompt, verbose, safeMode, onNavigate }: REPLProps) {
  const session = useSession(peer)
  const {
    messages,
    isLoading,
    toolUseConfirm,
    totalCost,
    usageStats,
    planState,
    lastError,
    submit,
    abort,
    resolvePermission,
    addLocalMessage,
    clearMessages,
  } = session

  const { exit } = useApp()
  const [sessionStart] = useState(() => Date.now())

  // ESC - cancel if loading (global handler; PromptInput has its own useInput)
  useInput((_input, key) => {
    if (key.escape && isLoading) {
      abort()
    }
  })

  // Handle initial prompt
  useEffect(() => {
    if (initialPrompt) {
      void submit(initialPrompt)
    }
  }, [])

  // Message normalization pipeline
  const normalizedMessages = useMemo(() => {
    const normalized = normalizeMessages(messages)
    return reorderMessages(normalized)
  }, [messages])

  // Static/transient split for Ink performance
  const staticPrefixLength = useMemo(
    () => getStaticPrefixLength(normalizedMessages),
    [normalizedMessages],
  )

  const staticMessages = useMemo(
    () => normalizedMessages.slice(0, staticPrefixLength),
    [normalizedMessages, staticPrefixLength],
  )

  const transientMessages = useMemo(
    () => normalizedMessages.slice(staticPrefixLength),
    [normalizedMessages, staticPrefixLength],
  )

  // Prepend logo sentinel to static items so it stays at scrollback top
  const staticItemsWithLogo = useMemo(
    (): StaticItem[] => [LOGO_ITEM, ...staticMessages],
    [staticMessages],
  )

  const handleSubmit = useCallback(
    (text: string) => {
      if (!text.trim()) return
      const trimmed = text.trim()
      const cmd = trimmed.toLowerCase()

      // --- Built-in slash commands (instant, no LLM round-trip) ---
      if (cmd === "/doctor" && onNavigate) {
        onNavigate("doctor")
        return
      }

      if (cmd === "/help") {
        addLocalMessage(trimmed, HELP_TEXT)
        return
      }

      if (cmd === "/clear") {
        clearMessages()
        addLocalMessage(trimmed, "Conversation cleared.")
        // Also tell the backend to clear its message history
        void peer.sendRequest({ method: "session/submit", params: { prompt: "/clear" } }).catch(() => {})
        return
      }

      if (cmd === "/model") {
        void (async () => {
          try {
            const res = await peer.sendRequest({ method: "config/get", params: { key: "model" } }) as { value?: string }
            addLocalMessage(trimmed, `Current model: ${res?.value ?? "unknown"}`)
          } catch {
            addLocalMessage(trimmed, "Could not retrieve model info.")
          }
        })()
        return
      }

      void submit(text)
    },
    [submit, onNavigate, addLocalMessage, clearMessages, peer],
  )

  const handlePermissionDecision = useCallback(
    (decision: PermissionDecision) => {
      void resolvePermission(decision)
    },
    [resolvePermission],
  )

  // Session duration (updated each render)
  const elapsed = Math.floor((Date.now() - sessionStart) / 1000)
  const durationStr = elapsed >= 60 ? `${Math.floor(elapsed / 60)}m${elapsed % 60}s` : `${elapsed}s`

  return (
    <Box flexDirection="column">
      {/* Static area: logo (first) + finalized messages — rendered once, pushed to scrollback */}
      <Static items={staticItemsWithLogo}>
        {(item: StaticItem) =>
          isLogoItem(item) ? (
            <Logo key="__logo__" theme={theme} />
          ) : (
            <MessageComponent
              key={item.id}
              message={item}
              theme={theme}
              verbose={verbose}
            />
          )
        }
      </Static>

      {/* Transient messages — re-render on state changes */}
      {transientMessages.map((message) => (
        <MessageComponent
          key={message.id}
          message={message}
          theme={theme}
          verbose={verbose}
        />
      ))}

      {/* Plan mode indicator */}
      {planState && planState.isActive && (
        <PlanStatusBar planState={planState} theme={theme} />
      )}

      {/* Permission dialog */}
      {toolUseConfirm && (
        <PermissionRequest
          confirm={toolUseConfirm}
          theme={theme}
          onDecision={handlePermissionDecision}
        />
      )}

      {/* Loading indicator */}
      {isLoading && !toolUseConfirm && (
        <Box marginTop={1}>
          <Spinner label="Thinking..." color={theme.thinking} />
        </Box>
      )}

      {/* Separator line */}
      <Box marginTop={1}>
        <Text color={theme.muted}>{"─".repeat(process.stdout.columns || 80)}</Text>
      </Box>

      {/* Status bar — always visible with token stats */}
      <StatusBar
        totalCost={totalCost}
        usageStats={usageStats}
        duration={durationStr}
        isLoading={isLoading}
        theme={theme}
      />

      {/* Input prompt */}
      {!toolUseConfirm && (
        <PromptInput
          theme={theme}
          isLoading={isLoading}
          onSubmit={handleSubmit}
          onExit={exit}
        />
      )}
    </Box>
  )
}

/** Format token count to human-readable (e.g. 1234 → "1.2K"). */
function formatTokens(n: number): string {
  if (n === 0) return "0"
  if (n < 1000) return String(n)
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}K`
  return `${(n / 1_000_000).toFixed(2)}M`
}

/** Status bar showing token usage, cost, and duration. */
function StatusBar({
  totalCost,
  usageStats,
  duration,
  isLoading,
  theme,
}: {
  totalCost: number
  usageStats: UsageStats
  duration: string
  isLoading: boolean
  theme: Theme
}) {
  return (
    <Box gap={1}>
      <Text color={theme.muted}>
        In: {formatTokens(usageStats.inputTokens)}
      </Text>
      <Text color={theme.muted}>│</Text>
      <Text color={theme.muted}>
        Out: {formatTokens(usageStats.outputTokens)}
      </Text>
      <Text color={theme.muted}>│</Text>
      <Text color={theme.muted}>
        Total: {formatTokens(usageStats.totalTokens)}
      </Text>
      <Text color={theme.muted}>│</Text>
      <Text color={theme.secondaryText}>
        ΣTotal: {formatTokens(usageStats.cumulativeTotalTokens)}
      </Text>
      <Text color={theme.muted}>│</Text>
      <Text color={theme.cost}>
        ${totalCost.toFixed(4)}
      </Text>
      <Text color={theme.muted}>│</Text>
      <Text color={theme.muted}>
        {duration}
      </Text>
      {isLoading && (
        <>
          <Text color={theme.muted}>│</Text>
          <Text color={theme.thinking}>⟳</Text>
        </>
      )}
    </Box>
  )
}

/** Plan mode progress indicator. */
function PlanStatusBar({ planState, theme }: { planState: PlanState; theme: Theme }) {
  const completed = planState.steps.filter((s) => s.status === "completed").length
  const total = planState.steps.length

  return (
    <Box flexDirection="column" marginTop={1}>
      <Text color={theme.planMode} bold>
        Plan: {planState.objective}
      </Text>
      <Text color={theme.muted}>
        {completed}/{total} steps completed
      </Text>
    </Box>
  )
}
