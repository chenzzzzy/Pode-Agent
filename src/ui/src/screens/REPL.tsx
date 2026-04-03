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
import type { Theme, Message, PermissionDecision } from "../types.js"
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
}

export function REPL({ peer, theme, initialPrompt, verbose, safeMode }: REPLProps) {
  const session = useSession(peer)
  const {
    messages,
    isLoading,
    toolUseConfirm,
    totalCost,
    planState,
    lastError,
    submit,
    abort,
    resolvePermission,
  } = session

  const { exit } = useApp()
  const [showWelcome, setShowWelcome] = useState(true)
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
      setShowWelcome(false)
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

  const handleSubmit = useCallback(
    (text: string) => {
      if (!text.trim()) return
      setShowWelcome(false)
      void submit(text)
    },
    [submit],
  )

  const handlePermissionDecision = useCallback(
    (decision: PermissionDecision) => {
      void resolvePermission(decision)
    },
    [resolvePermission],
  )

  // Session duration
  const elapsed = Math.floor((Date.now() - sessionStart) / 1000)
  const durationStr = elapsed >= 60 ? `${Math.floor(elapsed / 60)}m${elapsed % 60}s` : `${elapsed}s`

  return (
    <Box flexDirection="column">
      {/* Welcome banner */}
      {showWelcome && <Logo theme={theme} />}

      {/* Static messages — rendered once, never re-rendered */}
      {staticMessages.length > 0 && (
        <Static items={staticMessages}>
          {(message) => (
            <MessageComponent
              key={message.id}
              message={message}
              theme={theme}
              verbose={verbose}
            />
          )}
        </Static>
      )}

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

      {/* Status bar */}
      <StatusBar
        totalCost={totalCost}
        duration={durationStr}
        isLoading={isLoading}
        theme={theme}
        messageCount={normalizedMessages.length}
      />

      {/* Input prompt */}
      {!toolUseConfirm && (
        <PromptInput
          theme={theme}
          isLoading={isLoading}
          onSubmit={handleSubmit}
        />
      )}
    </Box>
  )
}

/** Status bar showing cost, session duration, and message count. */
function StatusBar({
  totalCost,
  duration,
  isLoading,
  theme,
  messageCount,
}: {
  totalCost: number
  duration: string
  isLoading: boolean
  theme: Theme
  messageCount: number
}) {
  if (totalCost === 0 && !isLoading) return null

  return (
    <Box marginTop={0} gap={2}>
      {totalCost > 0 && (
        <Text color={theme.cost}>
          ${totalCost.toFixed(4)}
        </Text>
      )}
      {messageCount > 0 && (
        <Text color={theme.muted}>
          {messageCount} msgs
        </Text>
      )}
      <Text color={theme.muted}>
        {duration}
      </Text>
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
