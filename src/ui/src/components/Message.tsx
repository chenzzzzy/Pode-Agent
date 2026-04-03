/**
 * Message component — dispatcher that routes to the correct sub-component
 * based on message role and type.
 *
 * This is the initial simplified version. Task 4.3 will port all 15+
 * message type components from Kode-Agent.
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

export interface MessageProps {
  message: MessageType
  theme: Theme
  verbose?: boolean
}

export function Message({ message, theme, verbose }: MessageProps) {
  switch (message.role) {
    case "user":
      return <UserMessageRenderer message={message} theme={theme} />
    case "assistant":
      return <AssistantMessageRenderer message={message} theme={theme} verbose={verbose} />
    default:
      return null
  }
}

function UserMessageRenderer({ message, theme }: { message: MessageType; theme: Theme }) {
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
      return (
        <Box paddingLeft={2} marginTop={0}>
          <Text color={color}>
            {"  "}[{label}] {m.toolName}
          </Text>
          {m.output && (
            <Text color={theme.muted}> {truncate(m.output, 200)}</Text>
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
          <Text>{m.text}</Text>
          {m.costUsd !== undefined && m.costUsd > 0 && (
            <Text color={theme.cost}> Cost: ${m.costUsd.toFixed(4)}</Text>
          )}
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
            <Text color={theme.muted}>{m.output}</Text>
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

function truncate(s: string, maxLen: number): string {
  const oneLine = s.replace(/\n/g, "\\n")
  if (oneLine.length <= maxLen) return oneLine
  return oneLine.slice(0, maxLen - 3) + "..."
}
