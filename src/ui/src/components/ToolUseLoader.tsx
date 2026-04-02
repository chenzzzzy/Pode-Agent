/**
 * ToolUseLoader — animated indicator for tool use execution state.
 *
 * Ported from Kode-Agent/src/ui/components/ToolUseLoader.tsx
 * Shows a blinking dot when a tool is executing, steady when completed/failed.
 */

import React, { useState, useEffect } from "react"
import { Text } from "ink"

export interface ToolUseLoaderProps {
  isError?: boolean
  isUnresolved?: boolean
  shouldAnimate?: boolean
}

const BLINK_FRAMES = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]

export function ToolUseLoader({
  isError = false,
  isUnresolved = false,
  shouldAnimate = true,
}: ToolUseLoaderProps) {
  const [frame, setFrame] = useState(0)

  useEffect(() => {
    if (!shouldAnimate) return
    const id = setInterval(() => {
      setFrame((f) => (f + 1) % BLINK_FRAMES.length)
    }, 80)
    return () => clearInterval(id)
  }, [shouldAnimate])

  if (isError) {
    return <Text color="red">✗</Text>
  }

  if (isUnresolved && shouldAnimate) {
    return <Text color="yellow">{BLINK_FRAMES[frame]}</Text>
  }

  if (isUnresolved) {
    return <Text color="yellow">○</Text>
  }

  return <Text color="green">✓</Text>
}
