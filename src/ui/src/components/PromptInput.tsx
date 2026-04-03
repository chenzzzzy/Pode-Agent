/**
 * PromptInput — terminal input component with cursor editing.
 *
 * Uses a combined { value, cursor } state with functional updates
 * to guarantee stale-closure safety on rapid key presses.
 *
 * Key bindings:
 * - Arrow keys: left/right move cursor, up/down jump to start/end
 * - Ctrl+a/e: start/end of line
 * - Ctrl+u/k: kill before/after cursor
 * - Ctrl+w: delete word before cursor
 * - Ctrl+l: clear input
 * - Ctrl+C: clear input if has text, otherwise exit
 * - Escape: clear input if has text, otherwise exit
 * - Enter: submit
 */

import React, { useCallback, useRef, useState, useEffect } from "react"
import { Box, Text, useInput } from "ink"
import figures from "figures"
import type { Theme } from "../types.js"

export interface PromptInputProps {
  theme: Theme
  isLoading: boolean
  onSubmit: (text: string) => void
  onExit?: () => void
}

/** Combined state avoids stale closures between rapid key presses. */
interface InputState {
  value: string
  cursor: number
}

/** Max command history entries kept in memory. */
const MAX_HISTORY = 1000

export function PromptInput({ theme, isLoading, onSubmit, onExit }: PromptInputProps) {
  const [input, setInput] = useState<InputState>({ value: "", cursor: 0 })
  const historyRef = useRef<string[]>([])
  // pendingSubmit: set by Enter key, consumed by effect to avoid setState-in-render
  const [pendingSubmit, setPendingSubmit] = useState<string | null>(null)

  const handleSubmit = useCallback(
    (text: string) => {
      if (!text.trim()) return

      // Append to history, deduplicating
      const newHistory = historyRef.current.filter((h) => h !== text)
      newHistory.push(text)
      if (newHistory.length > MAX_HISTORY) {
        newHistory.splice(0, newHistory.length - MAX_HISTORY)
      }
      historyRef.current = newHistory

      onSubmit(text)
      setInput({ value: "", cursor: 0 })
    },
    [onSubmit],
  )

  // Process pending submit outside of render cycle
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
          // Single Ctrl+C: clear input if has text, otherwise exit
          setInput((prev) => {
            if (prev.value) {
              return { value: "", cursor: 0 }
            }
            // Input is empty — exit
            onExit?.()
            return prev
          })
          return
        }
        case "a": // Move to start
          setInput((prev) => ({ ...prev, cursor: 0 }))
          return
        case "e": // Move to end
          setInput((prev) => ({ ...prev, cursor: prev.value.length }))
          return
        case "u": // Kill line before cursor
          setInput((prev) => ({
            value: prev.value.slice(prev.cursor),
            cursor: 0,
          }))
          return
        case "k": // Kill line after cursor
          setInput((prev) => ({
            value: prev.value.slice(0, prev.cursor),
            cursor: prev.cursor,
          }))
          return
        case "w": // Delete word before cursor
          setInput((prev) => {
            if (prev.cursor === 0) return prev
            const beforeCursor = prev.value.slice(0, prev.cursor)
            const match = beforeCursor.match(/\S+\s*$/)
            const deleteCount = match ? match[0].length : 0
            const newCursor = prev.cursor - deleteCount
            return {
              value: prev.value.slice(0, newCursor) + prev.value.slice(prev.cursor),
              cursor: Math.max(0, newCursor),
            }
          })
          return
        case "l": // Clear input
          setInput({ value: "", cursor: 0 })
          return
      }
      return
    }

    // --- Escape ---
    if (key.escape) {
      // Single Escape: clear input if has text, otherwise exit
      setInput((prev) => {
        if (prev.value) {
          return { value: "", cursor: 0 }
        }
        // Input is empty — exit
        onExit?.()
        return prev
      })
      return
    }

    // --- Enter ---
    if (key.return) {
      // Read current value and schedule submit via effect (not inside setState)
      setInput((prev) => {
        if (prev.value.trim()) {
          setPendingSubmit(prev.value)
        }
        return prev
      })
      return
    }

    // --- Backspace / Delete ---
    // Different terminals send different codes for Backspace:
    // - Some send \b (ASCII 8) → key.backspace
    // - Some send \x7f (ASCII 127) → key.delete
    // We treat both as "delete character before cursor"
    if (key.backspace || key.delete) {
      setInput((prev) => {
        if (prev.cursor === 0) return prev
        return {
          value: prev.value.slice(0, prev.cursor - 1) + prev.value.slice(prev.cursor),
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
      setInput((prev) => ({ ...prev, cursor: Math.min(prev.value.length, prev.cursor + 1) }))
      return
    }

    // --- Up/Down arrows: jump to start/end of line ---
    if (key.upArrow) {
      setInput((prev) => ({ ...prev, cursor: 0 }))
      return
    }
    if (key.downArrow) {
      setInput((prev) => ({ ...prev, cursor: prev.value.length }))
      return
    }

    // --- Regular text / paste ---
    if (inputChar && !key.ctrl && !key.meta) {
      const normalizedInput = inputChar.replace(/\r\n/g, "\n").replace(/\r/g, "\n")
      setInput((prev) => ({
        value:
          prev.value.slice(0, prev.cursor) + normalizedInput + prev.value.slice(prev.cursor),
        cursor: prev.cursor + normalizedInput.length,
      }))
    }
  })

  // Render prompt with cursor indicator
  const { value, cursor } = input
  const displayValue = value || ""
  const promptChar = `${figures.pointer} `

  return (
    <Box flexDirection="column" marginTop={1}>
      <Box>
        <Text color={theme.prompt} bold>
          {promptChar}
        </Text>
        {isLoading ? (
          <Text color={theme.muted}>(waiting...)</Text>
        ) : (
          <Text>
            {displayValue.slice(0, cursor)}
            <Text backgroundColor={theme.active}>{displayValue[cursor] ?? " "}</Text>
            {displayValue.slice(cursor + 1)}
          </Text>
        )}
      </Box>
    </Box>
  )
}
