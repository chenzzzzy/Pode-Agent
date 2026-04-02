/**
 * RequestStatusIndicator — shows animated status during API requests.
 *
 * Ported from Kode-Agent/src/ui/components/RequestStatusIndicator.tsx
 * Displays thinking/streaming/tool state with appropriate animation.
 */

import React, { useState, useEffect } from "react"
import { Box, Text } from "ink"
import type { Theme } from "../types.js"

export interface RequestStatusIndicatorProps {
  isLoading: boolean
  hasToolUse: boolean
  theme: Theme
}

const STATUS_MESSAGES = [
  "Thinking...",
  "Analyzing...",
  "Processing...",
  "Working...",
]

export function RequestStatusIndicator({
  isLoading,
  hasToolUse,
  theme,
}: RequestStatusIndicatorProps) {
  const [messageIndex, setMessageIndex] = useState(0)

  useEffect(() => {
    if (!isLoading) return
    const id = setInterval(() => {
      setMessageIndex((i) => (i + 1) % STATUS_MESSAGES.length)
    }, 3000)
    return () => clearInterval(id)
  }, [isLoading])

  if (!isLoading) return null

  return (
    <Box marginTop={1}>
      <Text color={theme.muted}>
        {hasToolUse ? "Executing tools..." : STATUS_MESSAGES[messageIndex]}
      </Text>
    </Box>
  )
}
