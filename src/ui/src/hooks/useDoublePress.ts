/**
 * useDoublePress — detects double-press of a key within a timeout window.
 *
 * Ported from Kode-Agent/src/ui/hooks/useDoublePress.ts
 * Returns [isFirstPress, onPress] where onPress triggers the detection.
 * isFirstPress is true between the first and second press (within timeout).
 */

import { useCallback, useRef, useState } from "react"

export function useDoublePress(timeoutMs = 1000): {
  isFirstPress: boolean
  onPress: () => boolean // returns true if this was the second press
  reset: () => void
} {
  const [isFirstPress, setIsFirstPress] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const reset = useCallback(() => {
    setIsFirstPress(false)
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const onPress = useCallback((): boolean => {
    if (isFirstPress) {
      // Second press within timeout
      reset()
      return true
    }

    // First press — start timeout
    setIsFirstPress(true)
    timerRef.current = setTimeout(() => {
      setIsFirstPress(false)
      timerRef.current = null
    }, timeoutMs)

    return false
  }, [isFirstPress, timeoutMs, reset])

  return { isFirstPress, onPress, reset }
}
