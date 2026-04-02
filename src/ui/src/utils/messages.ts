/**
 * Message normalization and reordering utilities.
 *
 * Adapted from Kode-Agent/src/utils/messages/core.ts for our flat message model.
 * Our messages are typed discriminated unions (AssistantTextMessage, etc.)
 * rather than raw API content blocks, so normalization is simpler.
 */

import type {
  Message,
  AssistantToolUseMessage,
  UserToolResultMessage,
  TaskProgressMessage,
} from "../types.js"

/** Filter out messages with empty text content. */
export function isNotEmptyMessage(message: Message): boolean {
  if (message.role === "assistant" && message.type === "text") {
    return message.text.trim().length > 0
  }
  if (message.role === "assistant" && message.type === "thinking") {
    return !message.isRedacted && message.text.trim().length > 0
  }
  return true
}

/**
 * Normalize messages: filter empty, then group related messages.
 * For our model, normalization is mostly filtering + ensuring consistency.
 */
export function normalizeMessages(messages: Message[]): Message[] {
  return messages.filter(isNotEmptyMessage)
}

/**
 * Build a set of tool_use_id values that have received a matching tool_result.
 */
function getToolResultIds(messages: Message[]): Map<string, boolean> {
  const result = new Map<string, boolean>()
  for (const msg of messages) {
    if (msg.role === "user" && msg.type === "tool_result") {
      result.set(msg.toolUseId, msg.resultStatus === "error")
    }
  }
  return result
}

/**
 * Get tool_use IDs that have been sent but not yet resolved with a tool_result.
 */
export function getUnresolvedToolUseIds(messages: Message[]): Set<string> {
  const toolResults = getToolResultIds(messages)
  const unresolved = new Set<string>()
  for (const msg of messages) {
    if (msg.role === "assistant" && msg.type === "tool_use") {
      if (!toolResults.has(msg.toolUseId)) {
        unresolved.add(msg.toolUseId)
      }
    }
  }
  return unresolved
}

/**
 * Get tool_use IDs that are currently in progress (started but no result yet).
 */
export function getInProgressToolUseIds(messages: Message[]): Set<string> {
  return getUnresolvedToolUseIds(messages)
}

/**
 * Reorder messages so that each tool_result appears immediately after its
 * corresponding tool_use message.
 */
export function reorderMessages(messages: Message[]): Message[] {
  const result: Message[] = []
  const toolUseIndex = new Map<string, number>() // toolUseId -> index in result

  for (const msg of messages) {
    if (msg.role === "assistant" && msg.type === "tool_use") {
      toolUseIndex.set(msg.toolUseId, result.length)
      result.push(msg)
    } else if (msg.role === "user" && msg.type === "tool_result") {
      const parentIdx = toolUseIndex.get(msg.toolUseId)
      if (parentIdx !== undefined) {
        // Insert right after the tool_use message (or after any existing
        // messages that were already inserted after it)
        let insertIdx = parentIdx + 1
        while (insertIdx < result.length) {
          const next = result[insertIdx]
          // Keep tool results and progress messages grouped together
          if (
            next.role === "user" &&
            next.type === "tool_result" &&
            toolUseIndex.has(next.toolUseId) &&
            toolUseIndex.get(next.toolUseId)! <= parentIdx
          ) {
            insertIdx++
          } else {
            break
          }
        }
        result.splice(insertIdx, 0, msg)
      } else {
        result.push(msg)
      }
    } else {
      result.push(msg)
    }
  }

  return result
}

/**
 * Calculate the static prefix length — the number of messages that should
 * be placed in Ink's <Static> component (rendered once, never re-rendered).
 * The latest message and any unresolved tool uses should be transient.
 */
export function getStaticPrefixLength(messages: Message[]): number {
  if (messages.length === 0) return 0

  const unresolvedIds = getUnresolvedToolUseIds(messages)
  let prefixEnd = messages.length

  // Keep the last message transient (it might be streaming)
  if (prefixEnd > 0) {
    prefixEnd--
  }

  // Keep any messages related to unresolved tool uses transient
  for (let i = prefixEnd; i >= 0; i--) {
    const msg = messages[i]
    if (
      (msg.role === "assistant" && msg.type === "tool_use" && unresolvedIds.has(msg.toolUseId)) ||
      (msg.role === "user" && msg.type === "tool_result" && msg.resultStatus === "error") ||
      (msg.role === "assistant" && msg.type === "task_progress")
    ) {
      prefixEnd = Math.min(prefixEnd, i)
    }
  }

  return Math.max(0, prefixEnd)
}
