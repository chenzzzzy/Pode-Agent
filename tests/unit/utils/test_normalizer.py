"""Tests for utils/messages/normalizer.py — Message format normalization."""

from __future__ import annotations

from pode_agent.core.config.schema import ProviderType
from pode_agent.services.ai.base import ToolUseBlock
from pode_agent.utils.messages.normalizer import (
    build_tool_result_message,
    extract_tool_uses,
    normalize_messages_for_provider,
    to_anthropic_messages,
    to_openai_messages,
)

# ---------------------------------------------------------------------------
# normalize_messages_for_provider
# ---------------------------------------------------------------------------


class TestNormalizeForProvider:
    def test_anthropic_routing(self) -> None:
        msgs = [{"role": "user", "content": "hello"}]
        result = normalize_messages_for_provider(msgs, ProviderType.ANTHROPIC)
        assert result == [{"role": "user", "content": "hello"}]

    def test_openai_routing(self) -> None:
        msgs = [{"role": "user", "content": "hello"}]
        result = normalize_messages_for_provider(msgs, ProviderType.OPENAI)
        assert result == [{"role": "user", "content": "hello"}]

    def test_bedrock_routing(self) -> None:
        msgs = [{"role": "user", "content": "hello"}]
        result = normalize_messages_for_provider(msgs, ProviderType.BEDROCK)
        assert result == [{"role": "user", "content": "hello"}]

    def test_unknown_provider_passes_through(self) -> None:
        msgs = [{"role": "user", "content": "hello"}]
        result = normalize_messages_for_provider(msgs, ProviderType.MISTRAL)
        assert result == msgs


# ---------------------------------------------------------------------------
# to_anthropic_messages
# ---------------------------------------------------------------------------


class TestToAnthropicMessages:
    def test_string_content(self) -> None:
        result = to_anthropic_messages([{"role": "user", "content": "hello"}])
        assert result == [{"role": "user", "content": "hello"}]

    def test_list_content(self) -> None:
        content = [{"type": "text", "text": "hi"}]
        result = to_anthropic_messages([{"role": "assistant", "content": content}])
        assert result == [{"role": "assistant", "content": content}]

    def test_dict_content_wrapped(self) -> None:
        content = {"type": "text", "text": "hi"}
        result = to_anthropic_messages([{"role": "user", "content": content}])
        assert result == [{"role": "user", "content": [content]}]

    def test_tool_result_gets_user_role(self) -> None:
        content = {"type": "tool_result", "tool_use_id": "tu_001", "content": "ok"}
        result = to_anthropic_messages([{"role": "assistant", "content": content}])
        assert result[0]["role"] == "user"

    def test_empty_content(self) -> None:
        result = to_anthropic_messages([{"role": "assistant", "content": ""}])
        assert result[0]["content"] == ""


# ---------------------------------------------------------------------------
# to_openai_messages
# ---------------------------------------------------------------------------


class TestToOpenAIMessages:
    def test_string_content(self) -> None:
        result = to_openai_messages([{"role": "user", "content": "hello"}])
        assert result == [{"role": "user", "content": "hello"}]

    def test_tool_call_id_creates_tool_message(self) -> None:
        msg = {
            "role": "assistant",
            "content": "result text",
            "tool_call_id": "call_001",
        }
        result = to_openai_messages([msg])
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "call_001"
        assert result[0]["content"] == "result text"

    def test_list_content(self) -> None:
        content = [{"type": "text", "text": "hi"}]
        result = to_openai_messages([{"role": "assistant", "content": content}])
        assert result[0]["content"] == content


# ---------------------------------------------------------------------------
# build_tool_result_message
# ---------------------------------------------------------------------------


class TestBuildToolResultMessage:
    def test_single_tool_use(self) -> None:
        tool_uses = [ToolUseBlock(id="tu_001", name="bash", input={"cmd": "ls"})]
        results = {"tu_001": "file1.txt\nfile2.txt"}

        msg = build_tool_result_message(tool_uses, results)
        assert msg["role"] == "user"
        assert len(msg["content"]) == 1
        assert msg["content"][0]["type"] == "tool_result"
        assert msg["content"][0]["tool_use_id"] == "tu_001"
        assert msg["content"][0]["content"] == "file1.txt\nfile2.txt"

    def test_multiple_tool_uses(self) -> None:
        tool_uses = [
            ToolUseBlock(id="tu_001", name="bash", input={}),
            ToolUseBlock(id="tu_002", name="file_read", input={}),
        ]
        results = {"tu_001": "output1", "tu_002": "output2"}

        msg = build_tool_result_message(tool_uses, results)
        assert len(msg["content"]) == 2

    def test_missing_result_empty_string(self) -> None:
        tool_uses = [ToolUseBlock(id="tu_001", name="bash", input={})]
        msg = build_tool_result_message(tool_uses, {})
        assert msg["content"][0]["content"] == ""

    def test_large_result_is_truncated_for_llm(self) -> None:
        tool_uses = [ToolUseBlock(id="tu_001", name="bash", input={})]
        results = {"tu_001": "\n".join(f"line {i}" for i in range(200))}

        msg = build_tool_result_message(tool_uses, results)

        content = msg["content"][0]["content"]
        assert "[truncated" in content
        assert "line 0" in content


# ---------------------------------------------------------------------------
# extract_tool_uses
# ---------------------------------------------------------------------------


class TestExtractToolUses:
    def test_list_content_with_tool_use(self) -> None:
        msg = {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me check"},
                {"type": "tool_use", "id": "tu_001", "name": "bash", "input": {"cmd": "ls"}},
            ],
        }
        blocks = extract_tool_uses(msg)
        assert len(blocks) == 1
        assert blocks[0].id == "tu_001"
        assert blocks[0].name == "bash"
        assert blocks[0].input == {"cmd": "ls"}

    def test_empty_content(self) -> None:
        blocks = extract_tool_uses({"role": "assistant", "content": ""})
        assert blocks == []

    def test_no_tool_uses(self) -> None:
        msg = {"role": "assistant", "content": [{"type": "text", "text": "Just text"}]}
        blocks = extract_tool_uses(msg)
        assert blocks == []

    def test_string_input_parsed(self) -> None:
        msg = {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "tu_001", "name": "bash", "input": '{"cmd": "ls"}'},
            ],
        }
        blocks = extract_tool_uses(msg)
        assert blocks[0].input == {"cmd": "ls"}

    def test_single_dict_tool_use(self) -> None:
        msg = {
            "role": "assistant",
            "content": {"type": "tool_use", "id": "tu_001", "name": "bash", "input": {"cmd": "ls"}},
        }
        blocks = extract_tool_uses(msg)
        assert len(blocks) == 1
        assert blocks[0].name == "bash"
