/**
 * useExitOnCtrlCD — exit on double Ctrl+C or Ctrl+D.
 * Ported from Kode-Agent src/ui/hooks/useExitOnCtrlCD.ts.
 */

import { useRef } from "react"
import { useInput, useApp } from "ink"

// Extend Ink's Key type to include 'c' and 'd' which are present at runtime
// but not included in the type definition
interface ExtendedKey {
  ctrl?: boolean
  c?: boolean
  d?: boolean
}

export function useExitOnCtrlCD() {
  const { exit } = useApp()
  const lastPressRef = useRef(0)

  useInput((_input, key) => {
    const now = Date.now()
    const extKey = key as unknown as ExtendedKey
    if (key.ctrl && (extKey.c || extKey.d)) {
      if (now - lastPressRef.current < 1000) {
        void exit()
      }
      lastPressRef.current = now
    }
  })
}
