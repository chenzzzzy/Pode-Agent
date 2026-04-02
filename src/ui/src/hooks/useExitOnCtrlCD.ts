/**
 * useExitOnCtrlCD — exit on double Ctrl+C or Ctrl+D.
 * Ported from Kode-Agent src/ui/hooks/useExitOnCtrlCD.ts.
 */

import { useInput, useApp } from "ink"

export function useExitOnCtrlCD() {
  const { exit } = useApp()
  let lastPress = 0

  useInput((_input, key) => {
    const now = Date.now()
    if (key.ctrl && (key.c || key.d)) {
      if (now - lastPress < 1000) {
        void exit()
      }
      lastPress = now
    }
  })
}
