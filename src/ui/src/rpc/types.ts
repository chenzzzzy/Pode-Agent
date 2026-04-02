/**
 * JSON-RPC protocol types for Pode-Agent UI ↔ Python bridge.
 *
 * These types define the contract between the TypeScript frontend
 * and the Python backend (ui_bridge.py).
 */

// --- Notification methods (Python → TypeScript) ---

export type SessionNotification =
  | { method: "session/user_message"; params: { text: string; message_id?: string } }
  | { method: "session/assistant_delta"; params: { text: string; message_id?: string } }
  | { method: "session/tool_use_start"; params: ToolUseStartParams }
  | { method: "session/tool_progress"; params: { tool_use_id: string; content: string } }
  | { method: "session/tool_result"; params: ToolResultParams }
  | { method: "session/permission_request"; params: PermissionRequestParams }
  | { method: "session/cost_update"; params: { cost_usd: number; total_usd: number } }
  | { method: "session/model_error"; params: { error: string; is_retryable?: boolean } }
  | { method: "session/done"; params: Record<string, never> }
  | { method: "plan/created"; params: PlanCreatedParams }
  | { method: "plan/approved"; params: { plan_id: string } }
  | { method: "plan/step_start"; params: { plan_id: string; step_index: number; step_title: string } }
  | { method: "plan/step_done"; params: { plan_id: string; step_index: number; result_summary?: string } }
  | { method: "plan/done"; params: { plan_id: string } }
  | { method: "plan/cancelled"; params: { plan_id: string; reason?: string } }

export type ToolUseStartParams = {
  tool_name: string
  tool_use_id: string
  tool_input: Record<string, unknown>
  message_id?: string
}

export type ToolResultParams = {
  tool_use_id: string
  data?: unknown
  is_error?: boolean
}

export type PermissionRequestParams = {
  tool_name: string
  tool_input: Record<string, unknown>
  tool_use_id: string
  risk_level: "low" | "medium" | "high"
  description?: string
}

export type PlanCreatedParams = {
  plan_id: string
  objective: string
  steps_count: number
  acceptance_criteria?: string[]
  risks?: string[]
}

// --- Request methods (TypeScript → Python) ---

export type PermissionDecision = "allow_once" | "allow_session" | "allow_always" | "deny"

export type SubmitParams = {
  prompt: string
  options?: {
    model?: string
    cwd?: string
  }
}

export type ResolvePermissionParams = {
  tool_use_id: string
  decision: PermissionDecision
}

export type RpcMethods = {
  "session/submit": { params: SubmitParams; result: { message_id: string } }
  "session/abort": { params: Record<string, never>; result: Record<string, never> }
  "session/resolve_permission": { params: ResolvePermissionParams; result: Record<string, never> }
  "session/get_messages": { params: Record<string, never>; result: { messages: unknown[] } }
  "session/get_cost": { params: Record<string, never>; result: { total_usd: number } }
  "config/get": { params: { key: string }; result: { value: unknown } }
  "config/set": { params: { key: string; value: string }; result: Record<string, never> }
  "session/list_logs": { params: Record<string, never>; result: { logs: string[] } }
  "session/load_log": { params: { log_name: string }; result: { messages: unknown[] } }
}
