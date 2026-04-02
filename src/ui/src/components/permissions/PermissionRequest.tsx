/**
 * PermissionRequest — dispatcher for tool permission dialogs.
 *
 * Routes to the appropriate tool-specific permission component
 * based on tool_name. Provides a fallback for unknown tools.
 *
 * Ported from Kode-Agent src/ui/components/permissions/PermissionRequest.tsx.
 * Adapted to receive tool info via JSON-RPC payload instead of Tool class instances.
 */

import React, { useCallback } from "react"
import { Box, Text, useInput } from "ink"
import type { Theme, ToolUseConfirm, PermissionDecision } from "../../types.js"

export interface PermissionRequestProps {
  confirm: ToolUseConfirm
  theme: Theme
  onDecision: (decision: PermissionDecision) => void
}

// Tool name → category mapping for routing to specialized displays
const TOOL_PERMISSION_MAP: Record<string, string> = {
  Bash: "bash",
  FileEdit: "file_edit",
  FileWrite: "file_write",
  FileRead: "filesystem",
  Glob: "filesystem",
  Grep: "filesystem",
  NotebookRead: "filesystem",
  NotebookEdit: "filesystem",
  MultiEdit: "file_edit",
  WebFetch: "web_fetch",
  WebSearch: "web_fetch",
  EnterPlanMode: "plan_mode",
  ExitPlanMode: "plan_mode",
  AskUserQuestion: "ask_user",
  SlashCommand: "slash_command",
  Skill: "skill",
  Ls: "filesystem",
}

export function PermissionRequest({ confirm, theme, onDecision }: PermissionRequestProps) {
  const toolCategory = TOOL_PERMISSION_MAP[confirm.toolName] ?? "fallback"

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor={getBorderColor(confirm.riskLevel, theme)}
      paddingX={1}
      marginTop={1}
    >
      <PermissionHeader confirm={confirm} theme={theme} />
      <ToolSpecificContent confirm={confirm} theme={theme} category={toolCategory} />
      {confirm.description && (
        <Box marginTop={0}>
          <Text color={theme.muted}> {confirm.description}</Text>
        </Box>
      )}
      <PermissionOptions confirm={confirm} theme={theme} onDecision={onDecision} />
    </Box>
  )
}

/** Header showing tool name, risk level, and optional risk score. */
function PermissionHeader({ confirm, theme }: { confirm: ToolUseConfirm; theme: Theme }) {
  const riskColor = getRiskColor(confirm.riskLevel, theme)
  const riskLabel = confirm.riskLevel.toUpperCase()

  return (
    <Box gap={1}>
      <Text color={theme.permission} bold>
        Permission Required
      </Text>
      <Text color={riskColor}>
        [{riskLabel}]
      </Text>
      <Text color={theme.tool}>{confirm.toolName}</Text>
    </Box>
  )
}

/** Tool-specific content rendering based on tool category. */
function ToolSpecificContent({
  confirm,
  theme,
  category,
}: {
  confirm: ToolUseConfirm
  theme: Theme
  category: string
}) {
  const input = confirm.toolInput

  switch (category) {
    case "bash":
      return <BashContent command={String(input.command ?? "")} theme={theme} />

    case "file_edit":
      return (
        <FileEditContent
          filePath={String(input.file_path ?? input.path ?? "")}
          oldString={input.old_string ? String(input.old_string) : undefined}
          newString={input.new_string ? String(input.new_string) : undefined}
          theme={theme}
        />
      )

    case "file_write":
      return (
        <FileWriteContent
          filePath={String(input.file_path ?? input.path ?? "")}
          content={input.content ? String(input.content) : undefined}
          theme={theme}
        />
      )

    case "filesystem":
      return (
        <Box marginTop={0}>
          <Text>
            {" "}
            Path: <Text color={theme.text}>{String(input.path ?? input.pattern ?? input.glob ?? "")}</Text>
          </Text>
        </Box>
      )

    case "web_fetch":
      return (
        <Box marginTop={0}>
          <Text>
            {" "}
            URL: <Text color={theme.text}>{String(input.url ?? input.query ?? "")}</Text>
          </Text>
        </Box>
      )

    case "plan_mode":
      return (
        <Box marginTop={0}>
          <Text color={theme.planMode}>
            {" "}
            {confirm.toolName === "EnterPlanMode"
              ? "Enter Plan Mode — AI will create a plan before executing"
              : "Exit Plan Mode — Plan complete"}
          </Text>
        </Box>
      )

    case "ask_user":
      return (
        <Box marginTop={0} flexDirection="column">
          {input.question && (
            <Text>
              {" "}
              Question: <Text color={theme.text}>{String(input.question)}</Text>
            </Text>
          )}
        </Box>
      )

    default:
      return (
        <Box marginTop={0}>
          <Text color={theme.muted}>
            {" "}
            {confirm.description ?? truncate(JSON.stringify(input), 120)}
          </Text>
        </Box>
      )
  }
}

/** Bash command content with safety warnings. */
function BashContent({ command, theme }: { command: string; theme: Theme }) {
  const isCompound = SHELL_CONNECTORS.some((c) => command.includes(c))
  const isDestructive = DESTRUCTIVE_PATTERNS.some((p) => command.includes(p))

  return (
    <Box flexDirection="column" marginTop={0}>
      <Text>
        {" "}
        <Text color={theme.bash}>$</Text> <Text color={theme.text}>{command}</Text>
      </Text>
      {isCompound && (
        <Text color={theme.warning}>
          {" "}
          Warning: Compound command (contains pipes/chaining)
        </Text>
      )}
      {isDestructive && (
        <Text color={theme.error}>
          {" "}
          Warning: Potentially destructive command
        </Text>
      )}
    </Box>
  )
}

/** File edit content with diff preview. */
function FileEditContent({
  filePath,
  oldString,
  newString,
  theme,
}: {
  filePath: string
  oldString?: string
  newString?: string
  theme: Theme
}) {
  return (
    <Box flexDirection="column" marginTop={0}>
      <Text>
        {" "}
        Edit: <Text color={theme.text}>{filePath}</Text>
      </Text>
      {oldString && (
        <DiffLines
          lines={oldString.split("\n")}
          type="removed"
          theme={theme}
          maxLines={5}
        />
      )}
      {newString && (
        <DiffLines
          lines={newString.split("\n")}
          type="added"
          theme={theme}
          maxLines={5}
        />
      )}
    </Box>
  )
}

/** File write content with line count. */
function FileWriteContent({
  filePath,
  content,
  theme,
}: {
  filePath: string
  content?: string
  theme: Theme
}) {
  const lineCount = content ? content.split("\n").length : 0
  const charCount = content?.length ?? 0

  return (
    <Box flexDirection="column" marginTop={0}>
      <Text>
        {" "}
        Write: <Text color={theme.text}>{filePath}</Text>
      </Text>
      <Text color={theme.muted}>
        {" "}
        {lineCount} lines, {charCount} chars
      </Text>
    </Box>
  )
}

/** Renders diff lines with +/- prefix and color. */
function DiffLines({
  lines,
  type,
  theme,
  maxLines = 5,
}: {
  lines: string[]
  type: "added" | "removed"
  theme: Theme
  maxLines?: number
}) {
  const prefix = type === "added" ? "+" : "-"
  const color = type === "added" ? theme.diffAdded : theme.diffRemoved
  const truncated = lines.length > maxLines ? [...lines.slice(0, maxLines), `... (${lines.length - maxLines} more lines)`] : lines

  return (
    <Box flexDirection="column">
      {truncated.map((line, i) => (
        <Text key={i} color={color}>
          {" "}
          {prefix} {truncate(line, 100)}
        </Text>
      ))}
    </Box>
  )
}

/** Permission options with keyboard shortcuts. */
function PermissionOptions({
  confirm,
  theme,
  onDecision,
}: {
  confirm: ToolUseConfirm
  theme: Theme
  onDecision: (decision: PermissionDecision) => void
}) {
  const options: { key: string; label: string; decision: PermissionDecision }[] = [
    { key: "y", label: "Allow Once", decision: "allow_once" },
    { key: "s", label: "Allow for Session", decision: "allow_session" },
    { key: "a", label: "Always Allow", decision: "allow_always" },
    { key: "n", label: "Reject (esc)", decision: "deny" },
  ]

  useInput((input, key) => {
    const option = options.find((o) => o.key === input.toLowerCase())
    if (option) {
      onDecision(option.decision)
    }
    if (key.escape) {
      onDecision("deny")
    }
  })

  return (
    <Box flexDirection="column" marginTop={1}>
      <Text color={theme.muted}>Do you want to proceed?</Text>
      {options.map((opt) => (
        <Text key={opt.key}>
          {" "}
          [<Text bold color={opt.decision === "deny" ? theme.warning : theme.success}>
            {opt.key.toUpperCase()}
          </Text>] {opt.label}
        </Text>
      ))}
    </Box>
  )
}

// --- Helpers ---

const SHELL_CONNECTORS = ["|", "&&", "||", ";", "$(", "`"]
const DESTRUCTIVE_PATTERNS = ["rm -rf", "rm -r", "rmdir", "format", "del /", "mkfs"]

function getRiskColor(level: string, theme: Theme): string {
  switch (level) {
    case "high":
      return theme.error
    case "medium":
      return theme.warning
    default:
      return theme.success
  }
}

function getBorderColor(level: string, theme: Theme): string {
  return getRiskColor(level, theme)
}

function truncate(s: string, maxLen: number): string {
  const oneLine = s.replace(/\n/g, "\\n")
  if (oneLine.length <= maxLen) return oneLine
  return oneLine.slice(0, maxLen - 3) + "..."
}
