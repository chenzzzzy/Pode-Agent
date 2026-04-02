/**
 * MessageResponse — wrapper component that renders children with visual indent.
 *
 * Ported from Kode-Agent/src/ui/components/MessageResponse.tsx
 * Used to visually nest tool results under their parent tool use.
 */

import React from "react"
import { Box, Text } from "ink"

export interface MessageResponseProps {
  children: React.ReactNode
}

export function MessageResponse({ children }: MessageResponseProps) {
  return (
    <Box flexDirection="row">
      <Text>
        {"  "}
        {"\u23BF"}{" "}
      </Text>
      <Box flexDirection="column" flexGrow={1}>
        {children}
      </Box>
    </Box>
  )
}
