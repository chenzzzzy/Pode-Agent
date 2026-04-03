/**
 * Logo component — displays the Pode-Agent welcome banner.
 * Ported from Kode-Agent src/ui/components/Logo.tsx + AsciiLogo.tsx.
 */

import React from "react"
import { Box, Text } from "ink"
import type { Theme } from "../theme.js"

const ASCII_LOGO = `  ____          _           _                    _
 |  _ \\ ___  __| | ___     / \\   __ _  ___ _ __ | |_
 | |_) / _ \\/ _\` |/ _ \\   / _ \\ / _\` |/ _ \\ '_ \\| __|
 |  __/ (_) | (_| |  __/  / ___ \\ (_| |  __/ | | | |_
 |_|   \\___/ \\__,_|\\___| /_/   \\_\\__, |\\___|_| |_|\\__|
                                  |___/`

export function Logo({ theme }: { theme: Theme }) {
  return (
    <Box flexDirection="column" marginTop={0} marginBottom={0}>
      <Text color={theme.kode} bold>
        {ASCII_LOGO}
      </Text>
      <Text color={theme.secondaryText}>
        {" "}AI-powered terminal coding assistant
      </Text>
      <Text color={theme.muted}>
        {" "}Type your question below, or /help for commands. Ctrl+C to exit.
      </Text>
    </Box>
  )
}
