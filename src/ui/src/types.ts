/**
 * Message and tool types shared across UI components.
 *
 * These types define the data structures used by the React + Ink UI
 * for rendering conversation history and tool interactions.
 */

export type MessageRole = "user" | "assistant"

export type ToolUseStatus = "queued" | "in_progress" | "completed" | "failed" | "rejected" | "canceled"

export type ToolResultStatus = "success" | "error" | "rejected" | "canceled"

export interface BaseMessage {
  id: string
  role: MessageRole
  timestamp: number
}

// --- Assistant messages ---

export interface AssistantTextMessage extends BaseMessage {
  role: "assistant"
  type: "text"
  text: string
  costUsd?: number
  durationMs?: number
}

export interface AssistantToolUseMessage extends BaseMessage {
  role: "assistant"
  type: "tool_use"
  toolName: string
  toolUseId: string
  toolInput: Record<string, unknown>
  status: ToolUseStatus
  output?: string
  error?: string
}

export interface AssistantThinkingMessage extends BaseMessage {
  role: "assistant"
  type: "thinking"
  text: string
  isRedacted?: boolean
}

// --- User messages ---

export interface UserTextMessage extends BaseMessage {
  role: "user"
  type: "text"
  text: string
}

export interface UserToolResultMessage extends BaseMessage {
  role: "user"
  type: "tool_result"
  toolUseId: string
  toolName: string
  resultStatus: ToolResultStatus
  output?: string
  error?: string
}

// --- Plan/Task messages ---

export type PlanStepState = {
  title: string
  status: "pending" | "in_progress" | "completed" | "failed"
  resultSummary?: string
}

export interface TaskProgressMessage extends BaseMessage {
  role: "assistant"
  type: "task_progress"
  planId: string
  steps: PlanStepState[]
}

// --- Error messages ---

export interface ErrorMessage extends BaseMessage {
  role: "assistant"
  type: "error"
  error: string
  isRetryable?: boolean
  hint?: string
}

// --- Union types ---

export type Message =
  | AssistantTextMessage
  | AssistantToolUseMessage
  | AssistantThinkingMessage
  | UserTextMessage
  | UserToolResultMessage
  | TaskProgressMessage
  | ErrorMessage

// --- Permission types ---

export type PermissionDecision = "allow_once" | "allow_session" | "allow_always" | "deny"

export interface ToolUseConfirm {
  toolName: string
  toolUseId: string
  toolInput: Record<string, unknown>
  riskLevel: "low" | "medium" | "high"
  description?: string
}

// --- Theme type (re-exported from theme.ts) ---

export type { Theme } from "./theme.js"
