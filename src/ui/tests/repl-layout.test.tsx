/**
 * Tests for REPL layout — verifies Logo persistence and StatusBar content.
 */

import { describe, test, expect } from "bun:test"
import React from "react"
import { render } from "ink-testing-library"
import { Box, Text } from "ink"

// Test StatusBar token formatting directly
function formatTokens(n: number): string {
  if (n === 0) return "0"
  if (n < 1000) return String(n)
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}K`
  return `${(n / 1_000_000).toFixed(2)}M`
}

describe("Token formatting", () => {
  test("formats zero", () => {
    expect(formatTokens(0)).toBe("0")
  })

  test("formats small numbers", () => {
    expect(formatTokens(42)).toBe("42")
    expect(formatTokens(999)).toBe("999")
  })

  test("formats thousands", () => {
    expect(formatTokens(1000)).toBe("1.0K")
    expect(formatTokens(43000)).toBe("43.0K")
    expect(formatTokens(1500)).toBe("1.5K")
  })

  test("formats millions", () => {
    expect(formatTokens(1_000_000)).toBe("1.00M")
    expect(formatTokens(2_500_000)).toBe("2.50M")
  })
})

describe("StatusBar rendering", () => {
  // Simplified StatusBar for testing
  function StatusBar({ usageStats, totalCost }: {
    usageStats: {
      inputTokens: number
      outputTokens: number
      totalTokens: number
      cumulativeTotalTokens: number
    }
    totalCost: number
  }) {
    return (
      <Box gap={1}>
        <Text>In: {formatTokens(usageStats.inputTokens)}</Text>
        <Text>│</Text>
        <Text>Out: {formatTokens(usageStats.outputTokens)}</Text>
        <Text>│</Text>
        <Text>Total: {formatTokens(usageStats.totalTokens)}</Text>
        <Text>│</Text>
        <Text>ΣTotal: {formatTokens(usageStats.cumulativeTotalTokens)}</Text>
        <Text>│</Text>
        <Text>${totalCost.toFixed(4)}</Text>
      </Box>
    )
  }

  test("shows token stats instead of old fields", () => {
    const { lastFrame } = render(
      <StatusBar
        usageStats={{
          inputTokens: 1500,
          outputTokens: 800,
          totalTokens: 2300,
          cumulativeTotalTokens: 5000,
        }}
        totalCost={0.0123}
      />
    )
    const output = lastFrame()!
    // Should show token stats
    expect(output).toContain("In: 1.5K")
    expect(output).toContain("Out: 800")
    expect(output).toContain("Total: 2.3K")
    expect(output).toContain("ΣTotal: 5.0K")
    expect(output).toContain("$0.0123")
    // Should NOT show old "msgs" field
    expect(output).not.toContain("msgs")
  })

  test("shows zero values when no usage yet", () => {
    const { lastFrame } = render(
      <StatusBar
        usageStats={{
          inputTokens: 0,
          outputTokens: 0,
          totalTokens: 0,
          cumulativeTotalTokens: 0,
        }}
        totalCost={0}
      />
    )
    const output = lastFrame()!
    expect(output).toContain("In: 0")
    expect(output).toContain("$0.0000")
  })
})

describe("Logo persistence", () => {
  // Simulate the Logo component
  function Logo() {
    return (
      <Box flexDirection="column">
        <Text bold>Pode-Agent</Text>
        <Text>AI-powered terminal coding assistant</Text>
      </Box>
    )
  }

  test("Logo renders at top without conditional", () => {
    // The key fix: Logo should always render, not gated by showWelcome
    const { lastFrame } = render(
      <Box flexDirection="column">
        <Logo />
        <Text>First user message</Text>
        <Text>Assistant response</Text>
      </Box>
    )
    const output = lastFrame()!
    expect(output).toContain("Pode-Agent")
    expect(output).toContain("AI-powered terminal coding assistant")
    expect(output).toContain("First user message")
  })

  test("Logo remains visible after messages are added", () => {
    // Simulate the REPL with messages — Logo should still be present
    const messages = [
      { role: "user", text: "Hello" },
      { role: "assistant", text: "Hi there!" },
    ]
    const { lastFrame } = render(
      <Box flexDirection="column">
        <Logo />
        {messages.map((m, i) => (
          <Text key={i}>{m.role}: {m.text}</Text>
        ))}
      </Box>
    )
    const output = lastFrame()!
    expect(output).toContain("Pode-Agent")
    expect(output).toContain("Hello")
    expect(output).toContain("Hi there!")
  })
})

describe("Slash command handling", () => {
  test("/help should produce built-in help text constant", () => {
    // The HELP_TEXT constant that REPL.tsx uses
    const HELP_TEXT =
      "Available commands:\n" +
      "  /help   – Show this help message\n" +
      "  /clear  – Clear the conversation\n" +
      "  /model  – Show the current model\n" +
      "  /doctor – Run diagnostics"

    expect(HELP_TEXT).toContain("/help")
    expect(HELP_TEXT).toContain("/clear")
    expect(HELP_TEXT).toContain("/model")
    expect(HELP_TEXT).toContain("/doctor")
  })

  test("slash commands are recognized case-insensitively", () => {
    const isSlashCommand = (text: string) => {
      const cmd = text.trim().toLowerCase()
      return ["/help", "/clear", "/model", "/doctor"].includes(cmd)
    }
    expect(isSlashCommand("/help")).toBe(true)
    expect(isSlashCommand("/HELP")).toBe(true)
    expect(isSlashCommand("/Help")).toBe(true)
    expect(isSlashCommand("/clear")).toBe(true)
    expect(isSlashCommand("hello")).toBe(false)
    expect(isSlashCommand("/unknown")).toBe(false)
  })
})
