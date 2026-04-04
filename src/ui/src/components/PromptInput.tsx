/**
 * PromptInput — terminal input component with grapheme-aware cursor editing.
 *
 * Uses Intl.Segmenter for grapheme cluster segmentation (CJK/emoji safe),
 * and string-width for accurate visible-width measurement in terminal.
 *
 * Key bindings:
 * - Arrow keys: left/right move cursor, up/down navigate history
 * - Ctrl+a/e: start/end of line
 * - Ctrl+u/k: kill before/after cursor
 * - Ctrl+w: delete word before cursor
 * - Ctrl+l: clear input
 * - Ctrl+C: clear input if has text, otherwise exit
 * - Escape: clear input if has text, otherwise exit
 * - Enter: submit
 */

import React, { useCallback, useRef, useState, useEffect, useMemo } from "react"
import { Box, Text, useInput } from "ink"
import figures from "figures"
import stringWidth from "string-width"
import type { Theme } from "../types.js"
import { useArrowKeyHistory } from "../hooks/useArrowKeyHistory.js"

export interface PromptInputProps {
  theme: Theme
  isLoading: boolean
  onSubmit: (text: string) => void
  onExit?: () => void
}

/**
 * Split a string into an array of grapheme clusters.
 * Uses Intl.Segmenter when available, falls back to Array.from().
 */
function toGraphemes(str: string): string[] {
  if (typeof Intl !== "undefined" && Intl.Segmenter) {
    const segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" })
    return Array.from(segmenter.segment(str), (s) => s.segment)
  }
  return Array.from(str)
}

/** Join grapheme array back to string. */
function fromGraphemes(graphemes: string[]): string {
  return graphemes.join("")
}

/** Combined state: grapheme array + cursor index (in grapheme units). */
interface InputState {
  graphemes: string[]
  cursor: number // index in graphemes array
}

function stateToString(state: InputState): string {
  return fromGraphemes(state.graphemes)
}

/** Max command history entries kept in memory. */
const MAX_HISTORY = 1000

export function PromptInput({ theme, isLoading, onSubmit, onExit }: PromptInputProps) {
  const [input, setInput] = useState<InputState>({ graphemes: [], cursor: 0 })
  const historyRef = useRef<string[]>([])
  const [pendingSubmit, setPendingSubmit] = useState<string | null>(null)

  // Arrow key history navigation
  const { onHistoryUp, onHistoryDown, resetHistory } = useArrowKeyHistory(stateToString(input))

  const handleSubmit = useCallback(
    (text: string) => {
      if (!text.trim()) return

      const newHistory = historyRef.current.filter((h) => h !== text)
      newHistory.push(text)
      if (newHistory.length > MAX_HISTORY) {
        newHistory.splice(0, newHistory.length - MAX_HISTORY)
      }
      historyRef.current = newHistory

      onSubmit(text)
      setInput({ graphemes: [], cursor: 0 })
      resetHistory()
    },
    [onSubmit],
  )

  useEffect(() => {
    if (pendingSubmit !== null) {
      handleSubmit(pendingSubmit)
      setPendingSubmit(null)
    }
  }, [pendingSubmit, handleSubmit])

  useInput((inputChar, key) => {
    if (isLoading) return

    // --- Ctrl shortcuts ---
    if (key.ctrl) {
      switch (inputChar) {
        case "c": {
          setInput((prev) => {
            if (prev.graphemes.length > 0) {
              return { graphemes: [], cursor: 0 }
            }
            onExit?.()
            return prev
          })
          return
        }
        case "a":
          setInput((prev) => ({ ...prev, cursor: 0 }))
          return
        case "e":
          setInput((prev) => ({ ...prev, cursor: prev.graphemes.length }))
          return
        case "u":
          setInput((prev) => ({
            graphemes: prev.graphemes.slice(prev.cursor),
            cursor: 0,
          }))
          return
        case "k":
          setInput((prev) => ({
            graphemes: prev.graphemes.slice(0, prev.cursor),
            cursor: prev.cursor,
          }))
          return
        case "w": {
          setInput((prev) => {
            if (prev.cursor === 0) return prev
            const before = fromGraphemes(prev.graphemes.slice(0, prev.cursor))
            const match = before.match(/\S+\s*$/)
            if (!match) return prev
            const deleteStr = match[0]
            const deleteGraphemes = toGraphemes(deleteStr).length
            const newCursor = Math.max(0, prev.cursor - deleteGraphemes)
            return {
              graphemes: [
                ...prev.graphemes.slice(0, newCursor),
                ...prev.graphemes.slice(prev.cursor),
              ],
              cursor: newCursor,
            }
          })
          return
        }
        case "l":
          setInput({ graphemes: [], cursor: 0 })
          return
      }
      return
    }

    // --- Escape ---
    if (key.escape) {
      setInput((prev) => {
        if (prev.graphemes.length > 0) {
          return { graphemes: [], cursor: 0 }
        }
        onExit?.()
        return prev
      })
      return
    }

    // --- Enter ---
    if (key.return) {
      setInput((prev) => {
        const text = stateToString(prev)
        if (text.trim()) {
          setPendingSubmit(text)
        }
        return prev
      })
      return
    }

    // --- Backspace / Delete ---
    if (key.backspace || key.delete) {
      setInput((prev) => {
        if (prev.cursor === 0) return prev
        return {
          graphemes: [
            ...prev.graphemes.slice(0, prev.cursor - 1),
            ...prev.graphemes.slice(prev.cursor),
          ],
          cursor: prev.cursor - 1,
        }
      })
      return
    }

    // --- Arrow keys ---
    if (key.leftArrow) {
      setInput((prev) => ({ ...prev, cursor: Math.max(0, prev.cursor - 1) }))
      return
    }
    if (key.rightArrow) {
      setInput((prev) => ({
        ...prev,
        cursor: Math.min(prev.graphemes.length, prev.cursor + 1),
      }))
      return
    }

    // --- Up/Down arrows: history navigation ---
    if (key.upArrow) {
      const reversedHistory = [...historyRef.current].reverse()
      const historyEntry = onHistoryUp(reversedHistory)
      if (historyEntry !== null) {
        const g = toGraphemes(historyEntry)
        setInput({ graphemes: g, cursor: g.length })
      }
      return
    }
    if (key.downArrow) {
      const reversedHistory = [...historyRef.current].reverse()
      const historyEntry = onHistoryDown(reversedHistory)
      if (historyEntry !== null) {
        const g = toGraphemes(historyEntry)
        setInput({ graphemes: g, cursor: g.length })
      } else {
        setInput({ graphemes: [], cursor: 0 })
      }
      return
    }

    // --- Regular text / paste ---
    if (inputChar && !key.ctrl && !key.meta) {
      const normalizedInput = inputChar.replace(/\r\n/g, "\n").replace(/\r/g, "\n")
      const newGraphemes = toGraphemes(normalizedInput)
      setInput((prev) => ({
        graphemes: [
          ...prev.graphemes.slice(0, prev.cursor),
          ...newGraphemes,
          ...prev.graphemes.slice(prev.cursor),
        ],
        cursor: prev.cursor + newGraphemes.length,
      }))
    }
  })

  // Render prompt with visible-width-aware cursor
  const { graphemes, cursor } = input
  const value = fromGraphemes(graphemes)
  const promptChar = `${figures.pointer} `

  // Compute visible portions for display, respecting terminal width
  const termCols = process.stdout.columns || 80
  const promptWidth = stringWidth(promptChar)
  const availWidth = Math.max(10, termCols - promptWidth - 2)

  // Split into before/at/after cursor based on grapheme index
  const beforeCursor = fromGraphemes(graphemes.slice(0, cursor))
  const atCursor = graphemes[cursor] ?? " "
  const afterCursor = fromGraphemes(graphemes.slice(cursor + 1))

  // Viewport clipping for long lines
  const beforeWidth = stringWidth(beforeCursor)
  const atWidth = stringWidth(atCursor)

  let displayBefore = beforeCursor
  let displayAt = atCursor
  let displayAfter = afterCursor

  if (beforeWidth + atWidth > availWidth) {
    // Cursor is past visible area — clip from left
    let accumulated = 0
    let startIdx = 0
    for (let i = 0; i < cursor; i++) {
      accumulated += stringWidth(graphemes[i])
      if (accumulated + atWidth > availWidth) {
        startIdx = i + 1
        accumulated -= stringWidth(graphemes[startIdx - 1])
      }
    }
    displayBefore = fromGraphemes(graphemes.slice(startIdx, cursor))
    // No room for after-cursor text
    displayAfter = ""
  } else {
    // Clip after-cursor if needed
    const remainWidth = availWidth - beforeWidth - atWidth
    if (stringWidth(afterCursor) > remainWidth) {
      let accum = 0
      let endIdx = 0
      const afterGraphemes = graphemes.slice(cursor + 1)
      for (let i = 0; i < afterGraphemes.length; i++) {
        const gw = stringWidth(afterGraphemes[i])
        if (accum + gw > remainWidth) break
        accum += gw
        endIdx = i + 1
      }
      displayAfter = fromGraphemes(afterGraphemes.slice(0, endIdx))
    }
  }

  const placeholder = "Type your message..."

  return (
    <Box flexDirection="column">
      <Box>
        <Text color={theme.prompt} bold>
          {promptChar}
        </Text>
        {isLoading ? (
          <Text color={theme.muted}>(waiting...)</Text>
        ) : graphemes.length === 0 ? (
          <Text>
            <Text backgroundColor={theme.active}>{" "}</Text>
            <Text color={theme.muted}> {placeholder}</Text>
          </Text>
        ) : (
          <Text>
            {displayBefore}
            <Text backgroundColor={theme.active}>{displayAt}</Text>
            {displayAfter}
          </Text>
        )}
      </Box>
    </Box>
  )
}
