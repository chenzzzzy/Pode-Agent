/**
 * Message component — dispatcher that routes to the correct sub-component
 * based on message role and type.
 *
 * Uses MarkdownText for assistant text to avoid raw markdown symbol leakage.
 * Tool results default to compact mode (one-line summary), verbose for full.
 */

import React from "react"
import { Box, Text } from "ink"
import type {
  Theme,
  Message as MessageType,
  AssistantTextMessage,
  AssistantToolUseMessage,
  AssistantThinkingMessage,
  UserTextMessage,
  UserToolResultMessage,
  TaskProgressMessage,
  ErrorMessage,
  SubAgentMessage,
} from "../types.js"
import { MarkdownText } from "./MarkdownText.js"

export interface MessageProps {
  message: MessageType
  theme: Theme
  verbose?: boolean
}

export function Message({ message, theme, verbose }: MessageProps) {
  switch (message.role) {
    case "user":
      return <UserMessageRenderer message={message} theme={theme} verbose={verbose} />
    case "assistant":
      return <AssistantMessageRenderer message={message} theme={theme} verbose={verbose} />
    default:
      return null
  }
}

function UserMessageRenderer({ message, theme, verbose }: { message: MessageType; theme: Theme; verbose?: boolean }) {
  if (message.role !== "user") return null

  switch (message.type) {
    case "text": {
      const m = message as UserTextMessage
      return (
        <Box flexDirection="column" marginTop={1}>
          <Text color={theme.prompt} bold>
            {">"} {m.text}
          </Text>
        </Box>
      )
    }
    case "tool_result": {
      const m = message as UserToolResultMessage
      const color =
        m.resultStatus === "success"
          ? theme.success
          : m.resultStatus === "error"
            ? theme.error
            : m.resultStatus === "rejected"
              ? theme.warning
              : theme.muted
      const label =
        m.resultStatus === "success"
          ? "OK"
          : m.resultStatus === "error"
            ? "ERROR"
            : m.resultStatus === "rejected"
              ? "REJECTED"
              : "CANCELED"

      // Compact mode: one-line summary. Verbose: full output.
      const compactOutput = m.output ? formatCompactOutput(m.output) : undefined
      return (
        <Box paddingLeft={2} marginTop={0} flexDirection="column">
          <Text color={color}>
            {"  "}[{label}] {m.toolName}
            {compactOutput && !verbose && (
              <Text color={theme.muted}> {compactOutput}</Text>
            )}
          </Text>
          {verbose && m.output && (
            <Box paddingLeft={4}>
              <Text color={theme.muted}>{formatVerboseOutput(m.output)}</Text>
            </Box>
          )}
        </Box>
      )
    }
    default:
      return null
  }
}

function AssistantMessageRenderer({
  message,
  theme,
  verbose,
}: {
  message: MessageType
  theme: Theme
  verbose?: boolean
}) {
  if (message.role !== "assistant") return null

  switch (message.type) {
    case "text": {
      const m = message as AssistantTextMessage
      return (
        <Box flexDirection="column" marginTop={1}>
          <MarkdownText text={m.text} theme={theme} />
        </Box>
      )
    }
    case "tool_use": {
      const m = message as AssistantToolUseMessage
      return (
        <Box marginTop={0} paddingLeft={2} flexDirection="column">
          <Text color={theme.tool}>
            {"  "}
            {getToolStatusIcon(m.status)} {m.toolName}(
            {formatToolInput(m.toolInput)})
          </Text>
          {m.output && verbose && (
            <Box paddingLeft={4}>
              <Text color={theme.muted}>{formatVerboseOutput(m.output)}</Text>
            </Box>
          )}
        </Box>
      )
    }
    case "thinking": {
      const m = message as AssistantThinkingMessage
      return (
        <Box marginTop={0} paddingLeft={2}>
          <Text color={theme.thinking}>
            {m.isRedacted ? "[thinking...]" : truncate(m.text, 200)}
          </Text>
        </Box>
      )
    }
    case "task_progress": {
      const m = message as TaskProgressMessage
      return (
        <Box flexDirection="column" marginTop={1}>
          <Text color={theme.planMode} bold>
            Plan Progress:
          </Text>
          {m.steps.map((step, i) => (
            <Text key={i}>
              {step.status === "completed"
                ? " ✓"
                : step.status === "in_progress"
                  ? " →"
                  : step.status === "failed"
                    ? " ✗"
                    : " ○"}{" "}
              {step.title}
            </Text>
          ))}
        </Box>
      )
    }
    case "error": {
      const m = message as ErrorMessage
      return (
        <Box
          flexDirection="column"
          marginTop={1}
          paddingX={1}
          borderStyle="round"
          borderColor={theme.error}
        >
          <Text color={theme.error} bold>
            ⚠ Error
          </Text>
          <Text color={theme.error}>{m.error}</Text>
          {m.isRetryable && (
            <Text color={theme.warning}>  (retryable — try again)</Text>
          )}
          {m.hint && (
            <Box marginTop={1}>
              <Text color={theme.warning} bold>
                💡 {m.hint}
              </Text>
            </Box>
          )}
        </Box>
      )
    }
    case "sub_agent": {
      const m = message as SubAgentMessage
      const statusIcon =
        m.status === "completed"
          ? "✓"
          : m.status === "failed"
            ? "✗"
            : m.status === "running"
              ? "◉"
              : "▸"
      const statusColor =
        m.status === "completed"
          ? theme.success
          : m.status === "failed"
            ? theme.error
            : theme.tool
      return (
        <Box flexDirection="column" marginTop={1} paddingLeft={2}>
          <Text color={statusColor}>
            {statusIcon} SubAgent ({m.subagentType}): {m.description}
          </Text>
          {m.status === "completed" && m.resultText && (
            <Box paddingLeft={2}>
              <Text color={theme.muted}>{truncate(m.resultText, 200)}</Text>
            </Box>
          )}
          {m.status === "completed" && m.durationMs !== undefined && (
            <Box paddingLeft={2}>
              <Text color={theme.muted}>
                Completed in {(m.durationMs / 1000).toFixed(1)}s
                {m.toolUseCount ? `, ${m.toolUseCount} tool calls` : ""}
              </Text>
            </Box>
          )}
          {m.status === "failed" && m.error && (
            <Box paddingLeft={2}>
              <Text color={theme.error}>{m.error}</Text>
            </Box>
          )}
        </Box>
      )
    }
    default:
      return null
  }
}

function getToolStatusIcon(status: string): string {
  switch (status) {
    case "queued":
      return "○"
    case "in_progress":
      return "◉"
    case "completed":
      return "✓"
    case "failed":
      return "✗"
    case "rejected":
      return "⊘"
    case "canceled":
      return "⊘"
    default:
      return "○"
  }
}

function formatToolInput(input: Record<string, unknown>): string {
  const entries = Object.entries(input)
  if (entries.length === 0) return ""
  if (entries.length === 1) {
    const val = String(entries[0][1])
    return truncate(val, 60)
  }
  return entries
    .slice(0, 2)
    .map(([k, v]) => `${k}=${truncate(String(v), 30)}`)
    .join(", ")
}

/** Format output for compact display — first meaningful line, truncated. */
function formatCompactOutput(output: string): string {
  // Try to parse JSON for prettier summary
  try {
    const parsed = JSON.parse(output)
    if (typeof parsed === "object" && parsed !== null) {
      const keys = Object.keys(parsed)
      if (keys.length <= 3) {
        return keys.map((k) => `${k}=${truncate(String(parsed[k]), 20)}`).join(", ")
      }
      return `{${keys.length} fields}`
    }
  } catch {
    // Not JSON, use as text
  }

  const firstLine = output.split(/\n/)[0] || ""
  return truncate(firstLine, 100)
}

/** Format output for verbose display — pretty-print JSON if possible. */
function formatVerboseOutput(output: string): string {
  try {
    const parsed = JSON.parse(output)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return output
  }
}

function truncate(s: string, maxLen: number): string {
  const oneLine = s.replace(/\n/g, " ").replace(/\s+/g, " ").trim()
  if (oneLine.length <= maxLen) return oneLine
  return oneLine.slice(0, maxLen - 3) + "..."
}
