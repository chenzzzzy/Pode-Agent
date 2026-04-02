/**
 * useArrowKeyHistory — up/down arrow history navigation hook.
 *
 * Ported from Kode-Agent/src/ui/hooks/useArrowKeyHistory.ts
 * Manages a 1-based index into a history array, saving the user's
 * current input before entering history mode and restoring it on exit.
 */

import { useCallback, useRef, useState } from "react"

export interface UseArrowKeyHistoryResult {
  historyIndex: number
  onHistoryUp: (history: string[]) => string | null
  onHistoryDown: (history: string[]) => string | null
  resetHistory: () => void
}

export function useArrowKeyHistory(currentInput: string): UseArrowKeyHistoryResult {
  const [historyIndex, setHistoryIndex] = useState(0)
  const lastTypedInput = useRef("")

  const onHistoryUp = useCallback(
    (history: string[]): string | null => {
      if (history.length === 0) return null

      // Save current input before entering history
      if (historyIndex === 0 && currentInput.trim()) {
        lastTypedInput.current = currentInput
      }

      const newIndex = historyIndex + 1
      if (newIndex > history.length) return null

      setHistoryIndex(newIndex)
      return history[newIndex - 1] ?? null
    },
    [historyIndex, currentInput],
  )

  const onHistoryDown = useCallback(
    (history: string[]): string | null => {
      if (historyIndex === 0) return null

      if (historyIndex === 1) {
        // Return to present — restore saved input
        setHistoryIndex(0)
        return lastTypedInput.current
      }

      const newIndex = historyIndex - 1
      setHistoryIndex(newIndex)
      return history[newIndex - 1] ?? null
    },
    [historyIndex],
  )

  const resetHistory = useCallback(() => {
    lastTypedInput.current = ""
    setHistoryIndex(0)
  }, [])

  return {
    historyIndex,
    onHistoryUp,
    onHistoryDown,
    resetHistory,
  }
}
