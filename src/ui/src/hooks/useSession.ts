/**
 * useSession — core hook for JSON-RPC communication with Python backend.
 *
 * Manages the JsonRpcPeer, subscribes to all notification methods,
 * translates notifications into React state updates, and provides
 * submit(), abort(), resolvePermission() methods.
 *
 * Ported from Kode-Agent's query loop pattern, adapted for JSON-RPC.
 */

import { useCallback, useEffect, useRef, useState } from "react"
import type { JsonRpcPeer } from "../rpc/client.js"
import type {
  Message,
  AssistantTextMessage,
  AssistantToolUseMessage,
  AssistantThinkingMessage,
  UserTextMessage,
  UserToolResultMessage,
  TaskProgressMessage,
  ErrorMessage,
  SubAgentMessage,
  PlanStepState,
  ToolUseConfirm,
  PermissionDecision,
} from "../types.js"

let nextMessageId = 1
function makeId(): string {
  return `msg_${nextMessageId++}_${Date.now()}`
}

export interface PlanState {
  planId: string
  objective: string
  steps: PlanStepState[]
  isActive: boolean
}

export function useSession(peer: JsonRpcPeer) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [toolUseConfirm, setToolUseConfirm] = useState<ToolUseConfirm | null>(null)
  const [totalCost, setTotalCost] = useState(0)
  const [planState, setPlanState] = useState<PlanState | null>(null)
  const [lastError, setLastError] = useState<string | null>(null)

  // Track active tool uses so we can update their status
  const activeToolUses = useRef<Map<string, AssistantToolUseMessage>>(new Map())
  // Track the current assistant message for streaming deltas
  const currentAssistantId = useRef<string | null>(null)

  // Register notification handlers
  useEffect(() => {
    // session/user_message — backend confirmation; skip if we already added it locally
    peer.registerMethod("session/user_message", (_params: unknown) => {
      // User message is already added locally in submit(), so ignore the backend echo
      // to avoid duplicate messages in the UI.
    })

    // session/assistant_delta — streaming text
    peer.registerMethod("session/assistant_delta", (params: unknown) => {
      const p = params as { text: string; message_id?: string }
      setMessages((prev) => {
        const last = prev[prev.length - 1]
        if (
          last &&
          last.role === "assistant" &&
          last.type === "text" &&
          last.id === currentAssistantId.current
        ) {
          return [
            ...prev.slice(0, -1),
            { ...last, text: (last as AssistantTextMessage).text + p.text },
          ]
        }
        const newId = p.message_id ?? makeId()
        currentAssistantId.current = newId
        const msg: AssistantTextMessage = {
          id: newId,
          role: "assistant",
          type: "text",
          text: p.text,
          timestamp: Date.now(),
        }
        return [...prev, msg]
      })
    })

    // session/tool_use_start
    peer.registerMethod("session/tool_use_start", (params: unknown) => {
      const p = params as {
        tool_name: string
        tool_use_id: string
        tool_input: Record<string, unknown>
        message_id?: string
      }
      const msg: AssistantToolUseMessage = {
        id: p.message_id ?? makeId(),
        role: "assistant",
        type: "tool_use",
        toolName: p.tool_name,
        toolUseId: p.tool_use_id,
        toolInput: p.tool_input,
        status: "in_progress",
        timestamp: Date.now(),
      }
      activeToolUses.current.set(p.tool_use_id, msg)
      currentAssistantId.current = null
      setMessages((prev) => [...prev, msg])
    })

    // session/tool_progress — update tool use message with progress content
    peer.registerMethod("session/tool_progress", (params: unknown) => {
      const p = params as { tool_use_id: string; content: string }
      const activeTool = activeToolUses.current.get(p.tool_use_id)
      if (activeTool) {
        setMessages((prev) =>
          prev.map((m) =>
            m.role === "assistant" && m.type === "tool_use" && m.toolUseId === p.tool_use_id
              ? { ...m, output: (m.output ?? "") + p.content }
              : m,
          ),
        )
      }
    })

    // session/tool_result
    peer.registerMethod("session/tool_result", (params: unknown) => {
      const p = params as {
        tool_use_id: string
        data?: unknown
        is_error?: boolean
      }
      const activeTool = activeToolUses.current.get(p.tool_use_id)

      const msg: UserToolResultMessage = {
        id: makeId(),
        role: "user",
        type: "tool_result",
        toolUseId: p.tool_use_id,
        toolName: activeTool?.toolName ?? "unknown",
        resultStatus: p.is_error ? "error" : "success",
        output: typeof p.data === "string"
        ? p.data
        : p.data != null
          ? JSON.stringify(p.data)
          : undefined,
        timestamp: Date.now(),
      }

      // Update the tool use message status
      if (activeTool) {
        activeToolUses.current.delete(p.tool_use_id)
        setMessages((prev) =>
          prev.map((m) =>
            m.role === "assistant" && m.type === "tool_use" && m.toolUseId === p.tool_use_id
              ? {
                  ...m,
                  status: (p.is_error ? "failed" : "completed") as AssistantToolUseMessage["status"],
                  output: msg.output,
                }
              : m,
          ),
        )
      }

      setMessages((prev) => [...prev, msg])
    })

    // session/permission_request
    peer.registerMethod("session/permission_request", (params: unknown) => {
      const p = params as {
        tool_name: string
        tool_input: Record<string, unknown>
        tool_use_id: string
        risk_level: "low" | "medium" | "high"
        description?: string
      }
      setToolUseConfirm({
        toolName: p.tool_name,
        toolUseId: p.tool_use_id,
        toolInput: p.tool_input,
        riskLevel: p.risk_level,
        description: p.description,
      })
    })

    // session/cost_update
    peer.registerMethod("session/cost_update", (params: unknown) => {
      const p = params as { cost_usd: number; total_usd: number }
      setTotalCost(p.total_usd)
    })

    // session/model_error
    peer.registerMethod("session/model_error", (params: unknown) => {
      const p = params as { error: string; is_retryable?: boolean }
      setLastError(p.error)

      // Provide helpful hints for common errors
      let hint: string | undefined
      const errLower = p.error.toLowerCase()
      if (errLower.includes("authentication") || errLower.includes("api key") || errLower.includes("unauthorized")) {
        hint = "Set your API key: export ANTHROPIC_API_KEY=sk-... or run: pode config set api_key <key>"
      } else if (errLower.includes("rate limit")) {
        hint = "Rate limited — wait a moment and try again."
      } else if (errLower.includes("connection")) {
        hint = "Check your network connection and proxy settings."
      }

      const msg: ErrorMessage = {
        id: makeId(),
        role: "assistant",
        type: "error",
        error: p.error,
        isRetryable: p.is_retryable,
        hint,
        timestamp: Date.now(),
      }
      setMessages((prev) => [...prev, msg])
    })

    // session/done
    peer.registerMethod("session/done", () => {
      setIsLoading(false)
      currentAssistantId.current = null
      setLastError(null)
    })

    // Plan mode notifications
    peer.registerMethod("plan/created", (params: unknown) => {
      const p = params as { plan_id: string; objective: string; steps_count: number }
      setPlanState({
        planId: p.plan_id,
        objective: p.objective,
        steps: Array.from({ length: p.steps_count }, (_, i) => ({
          title: `Step ${i + 1}`,
          status: "pending" as const,
        })),
        isActive: true,
      })
      const msg: AssistantTextMessage = {
        id: makeId(),
        role: "assistant",
        type: "text",
        text: `Plan created: ${p.objective} (${p.steps_count} steps)`,
        timestamp: Date.now(),
      }
      setMessages((prev) => [...prev, msg])
    })

    peer.registerMethod("plan/approved", (params: unknown) => {
      const p = params as { plan_id: string }
      setPlanState((prev) =>
        prev && prev.planId === p.plan_id ? { ...prev, isActive: true } : prev,
      )
    })

    peer.registerMethod("plan/step_start", (params: unknown) => {
      const p = params as { plan_id: string; step_index: number; step_title: string }
      setPlanState((prev) => {
        if (!prev || prev.planId !== p.plan_id) return prev
        const steps = [...prev.steps]
        if (p.step_index < steps.length) {
          steps[p.step_index] = { title: p.step_title || steps[p.step_index].title, status: "in_progress" }
        }
        return { ...prev, steps }
      })
      // Emit a progress update message for rendering
      setPlanState((prev) => {
        if (!prev || prev.planId !== p.plan_id) return prev
        const progressMsg: TaskProgressMessage = {
          id: makeId(),
          role: "assistant",
          type: "task_progress",
          planId: prev.planId,
          steps: prev.steps,
          timestamp: Date.now(),
        }
        setMessages((prevMsgs) => {
          const lastIdx = prevMsgs.findLastIndex((m) => m.role === "assistant" && m.type === "task_progress")
          if (lastIdx >= 0) {
            const updated = [...prevMsgs]
            updated[lastIdx] = progressMsg
            return updated
          }
          return [...prevMsgs, progressMsg]
        })
        return prev
      })
    })

    peer.registerMethod("plan/step_done", (params: unknown) => {
      const p = params as { plan_id: string; step_index: number; result_summary?: string }
      setPlanState((prev) => {
        if (!prev || prev.planId !== p.plan_id) return prev
        const steps = [...prev.steps]
        if (p.step_index < steps.length) {
          steps[p.step_index] = {
            ...steps[p.step_index],
            status: p.result_summary === undefined || !String(p.result_summary).includes("error") ? "completed" : "failed",
          }
        }
        const next = { ...prev, steps }
        // Update the task progress message in-place
        setMessages((prevMsgs) => {
          const lastIdx = prevMsgs.findLastIndex((m) => m.role === "assistant" && m.type === "task_progress")
          if (lastIdx >= 0) {
            const updated = [...prevMsgs]
            updated[lastIdx] = { ...updated[lastIdx], steps: next.steps } as TaskProgressMessage
            return updated
          }
          return prevMsgs
        })
        return next
      })
    })

    peer.registerMethod("plan/done", (params: unknown) => {
      const p = params as { plan_id: string }
      setPlanState((prev) =>
        prev && prev.planId === p.plan_id ? { ...prev, isActive: false } : null,
      )
      const msg: AssistantTextMessage = {
        id: makeId(),
        role: "assistant",
        type: "text",
        text: "Plan completed.",
        timestamp: Date.now(),
      }
      setMessages((prev) => [...prev, msg])
    })

    peer.registerMethod("plan/cancelled", (params: unknown) => {
      const p = params as { plan_id: string; reason?: string }
      setPlanState((prev) =>
        prev && prev.planId === p.plan_id ? { ...prev, isActive: false } : null,
      )
      const msg: AssistantTextMessage = {
        id: makeId(),
        role: "assistant",
        type: "text",
        text: p.reason ? `Plan cancelled: ${p.reason}` : "Plan cancelled.",
        timestamp: Date.now(),
      }
      setMessages((prev) => [...prev, msg])
    })

    // SubAgent lifecycle notifications
    peer.registerMethod("sub_agent/started", (params: unknown) => {
      const p = params as {
        agent_id: string
        subagent_type: string
        description: string
        tool_use_id: string
      }
      const msg: SubAgentMessage = {
        id: makeId(),
        role: "assistant",
        type: "sub_agent",
        agentId: p.agent_id,
        subagentType: p.subagent_type,
        description: p.description,
        status: "started",
        timestamp: Date.now(),
      }
      setMessages((prev) => [...prev, msg])
    })

    peer.registerMethod("sub_agent/progress", (params: unknown) => {
      const p = params as {
        agent_id: string
        subagent_type: string
        description: string
        progress_text: string
      }
      // Update existing SubAgent message in-place
      setMessages((prev) => {
        const idx = prev.findLastIndex(
          (m) => m.type === "sub_agent" && (m as SubAgentMessage).agentId === p.agent_id,
        )
        if (idx >= 0) {
          const updated = [...prev]
          updated[idx] = {
            ...updated[idx],
            description: p.progress_text || p.description,
            status: "running",
          } as SubAgentMessage
          return updated
        }
        return prev
      })
    })

    peer.registerMethod("sub_agent/completed", (params: unknown) => {
      const p = params as {
        agent_id: string
        subagent_type: string
        description: string
        result_text: string
        tool_use_count?: number
        duration_ms?: number
        tool_use_id: string
      }
      // Update existing SubAgent message to completed state
      setMessages((prev) => {
        const idx = prev.findLastIndex(
          (m) => m.type === "sub_agent" && (m as SubAgentMessage).agentId === p.agent_id,
        )
        const completedMsg: SubAgentMessage = {
          id: idx >= 0 ? prev[idx].id : makeId(),
          role: "assistant",
          type: "sub_agent",
          agentId: p.agent_id,
          subagentType: p.subagent_type,
          description: p.description,
          status: "completed",
          resultText: p.result_text,
          toolUseCount: p.tool_use_count,
          durationMs: p.duration_ms,
          timestamp: Date.now(),
        }
        if (idx >= 0) {
          const updated = [...prev]
          updated[idx] = completedMsg
          return updated
        }
        return [...prev, completedMsg]
      })
    })

    peer.registerMethod("sub_agent/failed", (params: unknown) => {
      const p = params as {
        agent_id: string
        subagent_type: string
        description: string
        error: string
        tool_use_id: string
      }
      setMessages((prev) => {
        const idx = prev.findLastIndex(
          (m) => m.type === "sub_agent" && (m as SubAgentMessage).agentId === p.agent_id,
        )
        const failedMsg: SubAgentMessage = {
          id: idx >= 0 ? prev[idx].id : makeId(),
          role: "assistant",
          type: "sub_agent",
          agentId: p.agent_id,
          subagentType: p.subagent_type,
          description: p.description,
          status: "failed",
          error: p.error,
          timestamp: Date.now(),
        }
        if (idx >= 0) {
          const updated = [...prev]
          updated[idx] = failedMsg
          return updated
        }
        return [...prev, failedMsg]
      })
    })
  }, [peer])

  const submit = useCallback(
    async (prompt: string) => {
      if (!prompt.trim()) return
      setIsLoading(true)
      setToolUseConfirm(null)
      setLastError(null)

      // Immediately add user message locally so it's visible right away
      const userMsg: UserTextMessage = {
        id: makeId(),
        role: "user",
        type: "text",
        text: prompt,
        timestamp: Date.now(),
      }
      setMessages((prev) => [...prev, userMsg])

      try {
        await peer.sendRequest({
          method: "session/submit",
          params: { prompt },
        })
      } catch (err) {
        setIsLoading(false)

        // Check for LLM setup validation errors from the backend
        const rpcErr = err as { code?: number; message?: string; data?: { setup_hints?: string[]; model?: string } }
        let errorText = err instanceof Error ? err.message : String(err)
        let hint: string | undefined

        if (rpcErr?.data?.setup_hints) {
          // LLM provider validation failed — show setup instructions
          errorText = `LLM provider not configured (model: ${rpcErr.data.model ?? "unknown"})`
          hint = rpcErr.data.setup_hints.join("\n")
        }

        const msg: ErrorMessage = {
          id: makeId(),
          role: "assistant",
          type: "error",
          error: errorText,
          hint,
          isRetryable: false,
          timestamp: Date.now(),
        }
        setMessages((prev) => [...prev, msg])
      }
    },
    [peer],
  )

  const abort = useCallback(async () => {
    try {
      await peer.sendRequest({ method: "session/abort" })
    } catch {
      // Ignore errors
    }
    setIsLoading(false)
  }, [peer])

  const resolvePermission = useCallback(
    async (decision: PermissionDecision) => {
      if (!toolUseConfirm) return
      const toolUseId = toolUseConfirm.toolUseId
      setToolUseConfirm(null)

      try {
        await peer.sendRequest({
          method: "session/resolve_permission",
          params: { tool_use_id: toolUseId, decision },
        })
      } catch {
        // Ignore errors
      }
    },
    [peer, toolUseConfirm],
  )

  return {
    messages,
    isLoading,
    toolUseConfirm,
    totalCost,
    planState,
    lastError,
    submit,
    abort,
    resolvePermission,
  }
}

/** Alias for backwards compatibility. */
export { useSession as useSessionCompat }
