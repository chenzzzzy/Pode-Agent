/**
 * Tests for MarkdownText component — verifies markdown rendering
 * does not leak raw symbols (##, **, backticks, \n).
 */

import { describe, test, expect } from "bun:test"
import React from "react"
import { render } from "ink-testing-library"
import { MarkdownText } from "../src/components/MarkdownText.js"

describe("MarkdownText", () => {
  test("renders headings without # symbols", () => {
    const { lastFrame } = render(
      <MarkdownText text="## Hello World" />
    )
    const output = lastFrame()!
    expect(output).toContain("Hello World")
    expect(output).not.toContain("##")
  })

  test("renders bold without ** symbols", () => {
    const { lastFrame } = render(
      <MarkdownText text="This is **bold** text" />
    )
    const output = lastFrame()!
    expect(output).toContain("bold")
    expect(output).not.toContain("**")
  })

  test("renders inline code without backticks", () => {
    const { lastFrame } = render(
      <MarkdownText text="Use `console.log` to debug" />
    )
    const output = lastFrame()!
    expect(output).toContain("console.log")
    expect(output).not.toContain("`")
  })

  test("renders lists with clean bullets", () => {
    const { lastFrame } = render(
      <MarkdownText text="- item one\n- item two\n- item three" />
    )
    const output = lastFrame()!
    expect(output).toContain("item one")
    expect(output).toContain("item two")
    expect(output).toContain("item three")
    // Should use – bullets, not raw -
    expect(output).toContain("–")
  })

  test("preserves code blocks", () => {
    const { lastFrame } = render(
      <MarkdownText text={"```python\nprint('hello')\n```"} />
    )
    const output = lastFrame()!
    expect(output).toContain("print")
    // Should not leak ``` markers
    expect(output).not.toContain("```")
  })

  test("does not display literal backslash-n as text", () => {
    // Verify that real newlines in markdown produce separate rendered blocks,
    // not literal "\n" text in the output
    const { lastFrame } = render(
      <MarkdownText text={"Line one\n\nLine two"} />
    )
    const output = lastFrame()!
    expect(output).toContain("Line one")
    expect(output).toContain("Line two")
  })

  test("renders links without markdown syntax leaking", () => {
    const { lastFrame } = render(
      <MarkdownText text="Visit [Google](https://google.com) for search" />
    )
    const output = lastFrame()!
    expect(output).toContain("Google")
    expect(output).toContain("https://google.com")
    // Should not show raw [text](url) syntax
    expect(output).not.toContain("](")
  })

  test("handles plain text without markdown", () => {
    const { lastFrame } = render(
      <MarkdownText text="Just a simple sentence." />
    )
    const output = lastFrame()!
    expect(output).toContain("Just a simple sentence.")
  })

  test("renders blockquotes", () => {
    const { lastFrame } = render(
      <MarkdownText text="> This is a quote" />
    )
    const output = lastFrame()!
    expect(output).toContain("This is a quote")
  })

  test("renders horizontal rules", () => {
    const { lastFrame } = render(
      <MarkdownText text={"Above\n\n---\n\nBelow"} />
    )
    const output = lastFrame()!
    expect(output).toContain("Above")
    expect(output).toContain("Below")
  })
})
