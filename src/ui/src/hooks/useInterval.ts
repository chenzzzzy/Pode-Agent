/**
 * useInterval — Dan Abramov-style interval hook with stable callback ref.
 *
 * Ported from Kode-Agent/src/ui/hooks/useInterval.ts
 */

import { useEffect, useRef } from "react"

export function useInterval(callback: () => void, delay: number): void {
  const savedCallback = useRef(callback)

  useEffect(() => {
    savedCallback.current = callback
  }, [callback])

  useEffect(() => {
    function tick() {
      savedCallback.current()
    }

    const id = setInterval(tick, delay)
    return () => clearInterval(id)
  }, [delay])
}
