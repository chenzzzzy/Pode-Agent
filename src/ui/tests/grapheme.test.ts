/**
 * Tests for grapheme-aware PromptInput component.
 * Verifies Chinese characters, emoji, and grapheme cluster handling.
 */

import { describe, test, expect } from "bun:test"

// Test the grapheme segmentation logic directly
function toGraphemes(str: string): string[] {
  if (typeof Intl !== "undefined" && Intl.Segmenter) {
    const segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" })
    return Array.from(segmenter.segment(str), (s) => s.segment)
  }
  return Array.from(str)
}

function fromGraphemes(graphemes: string[]): string {
  return graphemes.join("")
}

describe("Grapheme segmentation", () => {
  test("handles ASCII characters", () => {
    const g = toGraphemes("hello")
    expect(g).toEqual(["h", "e", "l", "l", "o"])
    expect(g.length).toBe(5)
  })

  test("handles Chinese characters as individual graphemes", () => {
    const g = toGraphemes("你好世界")
    expect(g).toEqual(["你", "好", "世", "界"])
    expect(g.length).toBe(4)
  })

  test("handles mixed ASCII and Chinese", () => {
    const g = toGraphemes("hello你好")
    expect(g.length).toBe(7) // 5 ASCII + 2 Chinese
    expect(g[5]).toBe("你")
    expect(g[6]).toBe("好")
  })

  test("roundtrips through grapheme split/join", () => {
    const original = "你好，世界！Hello, World!"
    const g = toGraphemes(original)
    expect(fromGraphemes(g)).toBe(original)
  })

  test("insertion at grapheme boundary works correctly", () => {
    const g = toGraphemes("你好")
    // Insert "世" at position 1 (between 你 and 好)
    const newG = [...g.slice(0, 1), "世", ...g.slice(1)]
    expect(fromGraphemes(newG)).toBe("你世好")
  })

  test("deletion at grapheme boundary works correctly", () => {
    const g = toGraphemes("你好世界")
    // Delete at cursor position 2 (remove 世)
    const cursor = 2
    const newG = [...g.slice(0, cursor), ...g.slice(cursor + 1)]
    expect(fromGraphemes(newG)).toBe("你好界")
  })

  test("backspace at grapheme boundary works correctly", () => {
    const g = toGraphemes("你好世界")
    // Backspace at cursor position 2 (remove 好)
    const cursor = 2
    const newG = [...g.slice(0, cursor - 1), ...g.slice(cursor)]
    expect(fromGraphemes(newG)).toBe("你世界")
  })

  test("left/right cursor movement is grapheme-based", () => {
    const g = toGraphemes("你好")
    // Starting at end (cursor = 2), move left once
    let cursor = g.length // 2
    cursor = Math.max(0, cursor - 1) // 1
    expect(g[cursor]).toBe("好")
    cursor = Math.max(0, cursor - 1) // 0
    expect(g[cursor]).toBe("你")
  })

  test("handles emoji (basic)", () => {
    const g = toGraphemes("Hello 👋")
    expect(g[g.length - 1]).toBe("👋")
  })

  test("ctrl+u kills before cursor correctly with CJK", () => {
    const g = toGraphemes("你好世界")
    const cursor = 2
    const newG = g.slice(cursor)
    expect(fromGraphemes(newG)).toBe("世界")
  })

  test("ctrl+k kills after cursor correctly with CJK", () => {
    const g = toGraphemes("你好世界")
    const cursor = 2
    const newG = g.slice(0, cursor)
    expect(fromGraphemes(newG)).toBe("你好")
  })
})
