/**
 * Cost — displays API cost and duration for a response.
 *
 * Ported from Kode-Agent/src/ui/components/Cost.tsx
 */

import React from "react"
import { Box, Text } from "ink"
import type { Theme } from "../types.js"

export interface CostProps {
  costUSD: number
  durationMs: number
  theme: Theme
}

export function Cost({ costUSD, durationMs, theme }: CostProps) {
  if (costUSD <= 0 && durationMs <= 0) return null

  const parts: string[] = []

  if (costUSD > 0) {
    parts.push(`$${costUSD.toFixed(4)}`)
  }

  if (durationMs > 0) {
    if (durationMs < 1000) {
      parts.push(`${durationMs}ms`)
    } else if (durationMs < 60_000) {
      parts.push(`${(durationMs / 1000).toFixed(1)}s`)
    } else {
      const mins = Math.floor(durationMs / 60_000)
      const secs = Math.floor((durationMs % 60_000) / 1000)
      parts.push(`${mins}m${secs}s`)
    }
  }

  return (
    <Box>
      <Text color={theme.cost}> {parts.join(" · ")}</Text>
    </Box>
  )
}
