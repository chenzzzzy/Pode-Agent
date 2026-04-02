/**
 * Help — displays available keyboard shortcuts and slash commands.
 *
 * Ported from Kode-Agent/src/ui/components/Help.tsx
 */

import React from "react"
import { Box, Text } from "ink"
import type { Theme } from "../types.js"

export interface HelpProps {
  theme: Theme
  onClose: () => void
}

const SHORTCUTS = [
  { key: "Enter", description: "Send message" },
  { key: "Escape", description: "Cancel / Clear input" },
  { key: "Ctrl+C", description: "Cancel request (2x to exit)" },
  { key: "Ctrl+D", description: "Exit (2x)" },
  { key: "Up/Down", description: "Navigate history" },
  { key: "Ctrl+A", description: "Move cursor to start" },
  { key: "Ctrl+E", description: "Move cursor to end" },
  { key: "Ctrl+U", description: "Delete line before cursor" },
  { key: "Ctrl+K", description: "Delete line after cursor" },
  { key: "Ctrl+W", description: "Delete word before cursor" },
  { key: "Ctrl+L", description: "Clear input" },
]

const SLASH_COMMANDS = [
  { command: "/help", description: "Show this help" },
  { command: "/config", description: "Manage configuration" },
  { command: "/model", description: "Switch model" },
  { command: "/clear", description: "Clear conversation" },
  { command: "/cost", description: "Show session cost" },
]

export function Help({ theme, onClose }: HelpProps) {
  return (
    <Box flexDirection="column" marginTop={1} paddingX={1}>
      <Text color={theme.kode} bold>
        Keyboard Shortcuts
      </Text>
      {SHORTCUTS.map((s) => (
        <Box key={s.key}>
          <Box width={14}>
            <Text color={theme.active}>{s.key}</Text>
          </Box>
          <Text color={theme.muted}>{s.description}</Text>
        </Box>
      ))}

      <Box marginTop={1}>
        <Text color={theme.kode} bold>
          Slash Commands
        </Text>
      </Box>
      {SLASH_COMMANDS.map((c) => (
        <Box key={c.command}>
          <Box width={14}>
            <Text color={theme.planMode}>{c.command}</Text>
          </Box>
          <Text color={theme.muted}>{c.description}</Text>
        </Box>
      ))}

      <Box marginTop={1}>
        <Text color={theme.muted}>Press Escape to close</Text>
      </Box>
    </Box>
  )
}
