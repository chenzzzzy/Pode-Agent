/**
 * Logo component — displays the Pode-Agent welcome banner.
 * Ported from Kode-Agent src/ui/components/Logo.tsx + AsciiLogo.tsx.
 */

import React from "react"
import { Box, Text } from "ink"
import type { Theme } from "../theme.js"

const ASCII_LOGO = `
  ____          _                   ____       _
 |  _ \\ __ _ __| |_ _ __ ___   __ _|  _ \\ __ _| |_ _____      ____ _ _
 | |_) / _\` / _\` | '_ \` _ \\ / _\` | |_) / _\` | __/ _ \\ \\ /\\ / / _\` '_|
 |  __/ (_| | (_| | | | | | | (_| |  __/ (_| | || (_) \\ V  V / (_| |
 |_|   \\__,_|\\__,_|_| |_| |_|\\__,_|_|   \\__,_|\\__\\___/ \\_/\\_/ \\__,_|
`

export function Logo({ theme }: { theme: Theme }) {
  return (
    <Box flexDirection="column" marginTop={0} marginBottom={1}>
      <Text color={theme.kode} bold>
        {ASCII_LOGO}
      </Text>
      <Text color={theme.secondaryText}>
        {" "}AI-powered terminal coding assistant (Python)
      </Text>
    </Box>
  )
}
