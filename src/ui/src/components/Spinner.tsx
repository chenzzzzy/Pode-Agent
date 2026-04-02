/**
 * Spinner component — loading animation.
 * Ported from Kode-Agent src/ui/components/Spinner.tsx.
 */

import React, { useState, useEffect } from "react"
import { Text } from "ink"
import figures from "figures"

const FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

export function Spinner({ label, color }: { label?: string; color?: string }) {
  const [frame, setFrame] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => {
      setFrame((f) => (f + 1) % FRAMES.length)
    }, 80)
    return () => clearInterval(timer)
  }, [])

  return (
    <Text color={color}>
      {FRAMES[frame]} {label ?? ""}
    </Text>
  )
}
