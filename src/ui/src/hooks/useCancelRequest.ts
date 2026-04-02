/**
 * useCancelRequest — cancel current request on ESC.
 * Ported from Kode-Agent src/ui/hooks/useCancelRequest.ts.
 */

import { useInput } from "ink"

export function useCancelRequest(isLoading: boolean, abort: () => void) {
  useInput((_input, key) => {
    if (key.escape && isLoading) {
      abort()
    }
  })
}
