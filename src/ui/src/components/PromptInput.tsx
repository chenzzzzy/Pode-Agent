/**
 * PromptInput — terminal input component with history navigation and editing.
 *
 * Enhanced version with:
 * - Up/down history navigation via useArrowKeyHistory
 * - Ctrl shortcuts (a/e for start/end, u/k for line kill, w for word delete)
 * - Home/End key support
 * - Paste handling (multi-char input)
 *
 * Full version (~860 lines) with tab completion, multi-line, and editor
 * integration deferred to a future iteration.
 */

import React, { useCallback, useRef, useState } from "react"
import { Box, Text, useInput } from "ink"
import figures from "figures"
import type { Theme } from "../types.js"
import { useArrowKeyHistory } from "../hooks/useArrowKeyHistory.js"
import { useDoublePress } from "../hooks/useDoublePress.js"

export interface PromptInputProps {
  theme: Theme
  isLoading: boolean
  onSubmit: (text: string) => void
  onExit?: () => void
}

/** Max command history entries kept in memory. */
const MAX_HISTORY = 1000

export function PromptInput({ theme, isLoading, onSubmit, onExit }: PromptInputProps) {
  const [value, setValue] = useState("")
  const [cursorIndex, setCursorIndex] = useState(0)
  const historyRef = useRef<string[]>([])

  const { onHistoryUp, onHistoryDown, resetHistory } = useArrowKeyHistory(value)

  // Double Ctrl+C to exit
  const { isFirstPress: firstCtrlC, onPress: onPressCtrlC } = useDoublePress(1000)
  const { isFirstPress: firstEscape, onPress: onPressEscape } = useDoublePress(500)

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
      setValue("")
      setCursorIndex(0)
      resetHistory()
    },
    [onSubmit, resetHistory],
  )

  useInput((input, key) => {
    if (isLoading) {
      // When loading, only handle Ctrl+C and Escape
      if (key.ctrl && input === "c") {
        onPressCtrlC()
        if (firstCtrlC) {
          onExit?.()
        }
      }
      if (key.escape) {
        onPressEscape()
      }
      return
    }

    // --- Ctrl shortcuts ---
    if (key.ctrl) {
      switch (input) {
        case "c":
          if (onPressCtrlC()) {
            onExit?.()
          } else {
            setValue("")
            setCursorIndex(0)
            resetHistory()
          }
          return
        case "a": // Move to start
          setCursorIndex(0)
          return
        case "e": // Move to end
          setCursorIndex(value.length)
          return
        case "u": // Kill line before cursor
          setValue(value.slice(cursorIndex))
          setCursorIndex(0)
          return
        case "k": // Kill line after cursor
          setValue(value.slice(0, cursorIndex))
          return
        case "w": // Delete word before cursor
          if (cursorIndex > 0) {
            const beforeCursor = value.slice(0, cursorIndex)
            const match = beforeCursor.match(/\S+\s*$/)
            const deleteCount = match ? match[0].length : 0
            const newCursor = cursorIndex - deleteCount
            setValue(value.slice(0, newCursor) + value.slice(cursorIndex))
            setCursorIndex(Math.max(0, newCursor))
          }
          return
        case "l": // Clear input
          setValue("")
          setCursorIndex(0)
          return
      }
      return
    }

    // --- Escape ---
    if (key.escape) {
      if (value) {
        setValue("")
        setCursorIndex(0)
        resetHistory()
      } else if (onPressEscape()) {
        onExit?.()
      }
      return
    }

    // --- Enter ---
    if (key.return) {
      if (value.trim()) {
        handleSubmit(value)
      }
      return
    }

    // --- Backspace ---
    if (key.backspace) {
      if (cursorIndex > 0) {
        setValue(value.slice(0, cursorIndex - 1) + value.slice(cursorIndex))
        setCursorIndex(cursorIndex - 1)
      }
      return
    }

    // --- Delete ---
    if (key.delete) {
      if (cursorIndex < value.length) {
        setValue(value.slice(0, cursorIndex) + value.slice(cursorIndex + 1))
      }
      return
    }

    // --- Arrow keys ---
    if (key.leftArrow) {
      setCursorIndex((i) => Math.max(0, i - 1))
      return
    }
    if (key.rightArrow) {
      setCursorIndex((i) => Math.min(value.length, i + 1))
      return
    }

    // --- History navigation ---
    if (key.upArrow) {
      const historyValue = onHistoryUp(historyRef.current)
      if (historyValue !== null) {
        setValue(historyValue)
        setCursorIndex(historyValue.length)
      }
      return
    }
    if (key.downArrow) {
      const historyValue = onHistoryDown(historyRef.current)
      if (historyValue !== null) {
        setValue(historyValue)
        setCursorIndex(historyValue.length)
      }
      return
    }

    // --- Home/End ---
    if (key.meta && input === "a") {
      setCursorIndex(0)
      return
    }

    // --- Regular text / paste ---
    if (input) {
      // Normalize line endings for paste
      const normalizedInput = input.replace(/\r\n/g, "\n").replace(/\r/g, "\n")
      // For paste (multi-char), just insert; don't submit on newlines
      const newValue = value.slice(0, cursorIndex) + normalizedInput + value.slice(cursorIndex)
      setValue(newValue)
      setCursorIndex(cursorIndex + normalizedInput.length)
    }
  })

  // Render prompt with cursor indicator
  const displayValue = value || ""
  const promptChar = `${figures.pointer} `

  return (
    <Box flexDirection="column" marginTop={1}>
      {/* Double-press exit warnings */}
      {firstCtrlC && (
        <Text color={theme.warning}>
          Press Ctrl+C again to exit
        </Text>
      )}
      {firstEscape && (
        <Text color={theme.warning}>
          Press Escape again to exit
        </Text>
      )}

      <Box>
        <Text color={theme.prompt} bold>
          {promptChar}
        </Text>
        {isLoading ? (
          <Text color={theme.muted}>(waiting...)</Text>
        ) : (
          <Text>
            {displayValue.slice(0, cursorIndex)}
            <Text backgroundColor={theme.active}>{displayValue[cursorIndex] ?? " "}</Text>
            {displayValue.slice(cursorIndex + 1)}
          </Text>
        )}
      </Box>
    </Box>
  )
}
