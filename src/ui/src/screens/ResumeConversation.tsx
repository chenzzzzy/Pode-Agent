/**
 * ResumeConversation — screen for selecting and resuming past sessions.
 *
 * Ported from Kode-Agent/src/ui/screens/ResumeConversation.tsx
 */

import React, { useState } from "react"
import { Box, Text, useInput } from "ink"
import figures from "figures"
import type { Theme } from "../types.js"

export interface LogEntry {
  name: string
  path: string
  date: string
  messageCount: number
}

export interface ResumeConversationProps {
  logs: LogEntry[]
  theme: Theme
  onSelect: (logPath: string) => void
  onBack: () => void
}

export function ResumeConversation({ logs, theme, onSelect, onBack }: ResumeConversationProps) {
  const [selectedIndex, setSelectedIndex] = useState(0)

  useInput((input, key) => {
    if (key.escape) {
      onBack()
      return
    }
    if (key.upArrow) {
      setSelectedIndex((i) => Math.max(0, i - 1))
      return
    }
    if (key.downArrow) {
      setSelectedIndex((i) => Math.min(logs.length - 1, i + 1))
      return
    }
    if (key.return && logs.length > 0) {
      onSelect(logs[selectedIndex].path)
    }
  })

  return (
    <Box flexDirection="column" paddingX={1}>
      <Text color={theme.kode} bold>
        Resume Conversation
      </Text>
      <Text color={theme.muted}>
        Select a past session to resume. Up/Down to navigate, Enter to select, Escape to go back.
      </Text>

      {logs.length === 0 ? (
        <Box marginTop={1}>
          <Text color={theme.muted}>No previous sessions found.</Text>
        </Box>
      ) : (
        <Box flexDirection="column" marginTop={1}>
          {logs.map((log, i) => (
            <Box key={log.path}>
              <Text color={i === selectedIndex ? theme.active : theme.muted}>
                {i === selectedIndex ? figures.pointer : " "}{" "}
                {log.date} — {log.name} ({log.messageCount} messages)
              </Text>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  )
}
