/**
 * StructuredDiff — renders a unified diff patch with colored +/- lines.
 *
 * Ported from Kode-Agent/src/ui/components/StructuredDiff.tsx
 * Uses the `diff` library's structured patch format.
 */

import React from "react"
import { Box, Text } from "ink"
import type { Theme } from "../types.js"

export interface Hunk {
  oldStart: number
  oldLines: number
  newStart: number
  newLines: number
  content: string
  changes: Change[]
}

export interface Change {
  type: "add" | "delete" | "normal"
  content: string
  oldNormalLineNumber?: number
  newNormalLineNumber?: number
}

export interface StructuredDiffProps {
  patch: Hunk
  dim?: boolean
  width?: number
  theme: Theme
}

export function StructuredDiff({ patch, dim = false, width, theme }: StructuredDiffProps) {
  const maxLineNum = Math.max(
    patch.oldStart + patch.oldLines,
    patch.newStart + patch.newLines,
  )
  const lineNumWidth = String(maxLineNum).length

  return (
    <Box flexDirection="column">
      {/* Hunk header */}
      <Text color={dim ? theme.muted : theme.text} bold>
        @@ -{patch.oldStart},{patch.oldLines} +{patch.newStart},{patch.newLines} @@
      </Text>

      {/* Changes */}
      {patch.changes.map((change, i) => (
        <DiffLine
          key={i}
          change={change}
          lineNumWidth={lineNumWidth}
          dim={dim}
          width={width}
          theme={theme}
        />
      ))}
    </Box>
  )
}

function DiffLine({
  change,
  lineNumWidth,
  dim,
  width,
  theme,
}: {
  change: Change
  lineNumWidth: number
  dim?: boolean
  width?: number
  theme: Theme
}) {
  const pad = (n: number | undefined) =>
    n !== undefined ? String(n).padStart(lineNumWidth) : " ".repeat(lineNumWidth)

  const oldNum = pad(change.type === "delete" ? change.oldNormalLineNumber : undefined)
  const newNum = pad(change.type === "add" ? change.newNormalLineNumber : change.type === "normal" ? change.newNormalLineNumber : undefined)

  let prefix: string
  let color: string | undefined
  switch (change.type) {
    case "add":
      prefix = "+"
      color = theme.diffAdded
      break
    case "delete":
      prefix = "-"
      color = theme.diffRemoved
      break
    default:
      prefix = " "
      color = dim ? theme.muted : theme.text
  }

  const content = truncateLine(change.content, width)

  return (
    <Text color={color}>
      {oldNum} {newNum} {prefix}{content}
    </Text>
  )
}

function truncateLine(line: string, maxWidth?: number): string {
  if (!maxWidth) return line
  // Account for line numbers + prefix (lineNumWidth * 2 + 3 spaces + 1 prefix)
  const available = maxWidth - 8
  if (available <= 0 || line.length <= available) return line
  return line.slice(0, available - 1) + "…"
}
