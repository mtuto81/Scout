"""Tests for native OpenAI-compatible tool calling and the JSON fallback."""

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import openai
import pytest

from agent import AsyncAIAgent
from tool_manager import AsyncToolManager


TEST_LLM_CONFIG = {
    "api_key": "test-key",
    "backend": "openrouter",
    "model": "test-model",
    "base_url": "https://api.openrouter.ai/v1",
}


def make_agent(**config_overrides):
    config = {**TEST_LLM_CONFIG, **config_overrides}
    with patch("agent.get_llm_config", return_value=config):
        return AsyncAIAgent()


class FakeStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def __aiter__(self):
        self._iterator = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration


def make_chunk(delta=None, finish_reason=None):
    if delta is None:
        delta = SimpleNamespace(content=None, reasoning_content=None)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)])


def content_chunk(text):
    return make_chunk(SimpleNamespace(content=text, reasoning_content=None))


def tool_call_delta(index=0, id=None, name=None, arguments=None):
    function = SimpleNamespace(name=name, arguments=arguments) if (name or arguments) else None
    return make_chunk(SimpleNamespace(
        tool_calls=[SimpleNamespace(index=index, id=id, function=function)],
        content=None,
        reasoning_content=None,
    ))


def register_add_tool(agent):
    agent.tool_manager.register({
        "name": "add",
        "description": "Add two numbers",
        "parameters": {
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        },
        "handler": lambda a, b: a + b,
    })


class TestNativeToolSchemas:
    def test_schemas_use_openai_function_format(self):
        agent = make_agent()
        register_add_tool(agent)

        schemas = agent._native_tool_schemas()

        add_schema = next(s for s in schemas if s["function"]["name"] == "add")
        assert add_schema["type"] == "function"
        assert add_schema["function"]["description"] == "Add two numbers"
        assert add_schema["function"]["parameters"]["required"] == ["a", "b"]
        assert add_schema["function"]["parameters"]["properties"]["a"] == {"type": "integer"}

    def test_native_tools_used_for_supported_backends(self):
        for backend in ("openrouter", "ollama", "local"):
            agent = make_agent(backend=backend)
            assert agent._use_native_tools() is True

    def test_native_tools_disabled_for_unknown_backend(self):
        agent = make_agent(backend="openai")
        assert agent._use_native_tools() is False

    def test_env_override_disables_native_tools(self):
        agent = make_agent()
        try:
            os.environ["SCOUT_DISABLE_NATIVE_TOOLS"] = "1"
            assert agent._use_native_tools() is False
        finally:
            os.environ.pop("SCOUT_DISABLE_NATIVE_TOOLS", None)


class TestNativeToolCallParsing:
    @pytest.mark.asyncio
    async def test_fragmented_stream_is_accumulated(self):
        agent = make_agent()

        stream = FakeStream([
            content_chunk("Let me calculate."),
            tool_call_delta(index=0, id="call_1", name="add"),
            tool_call_delta(index=0, arguments='{"a": 5'),
            tool_call_delta(index=0, arguments=', "b": 3}'),
            make_chunk(finish_reason="tool_calls"),
        ])

        content, raw_calls = await agent._collect_streamed_response(stream)

        assert content == "Let me calculate."
        assert len(raw_calls) == 1
        assert raw_calls[0]["id"] == "call_1"
        assert raw_calls[0]["name"] == "add"
        assert raw_calls[0]["arguments"] == '{"a": 5, "b": 3}'

    @pytest.mark.asyncio
    async def test_multiple_parallel_tool_calls(self):
        agent = make_agent()

        stream = FakeStream([
            tool_call_delta(index=0, id="call_1", name="add", arguments='{"a": 1, "b": 2}'),
            tool_call_delta(index=1, id="call_2", name="add", arguments='{"a": 3, "b": 4}'),
        ])

        _, raw_calls = await agent._collect_streamed_response(stream)

        assert [call["id"] for call in raw_calls] == ["call_1", "call_2"]

    def test_normalize_keeps_id_and_parses_args(self):
        agent = make_agent()

        calls = agent._normalize_native_tool_calls([
            {"id": "call_abc", "name": "add", "arguments": '{"a": 5, "b": 3}'},
        ])

        assert calls == [{"tool": "add", "args": {"a": 5, "b": 3}, "id": "call_abc"}]

    def test_normalize_repairs_trailing_comma_args(self):
        agent = make_agent()

        calls = agent._normalize_native_tool_calls([
            {"id": "call_1", "name": "add", "arguments": '{"a": 5, "b": 3,}'},
        ])

        assert calls[0]["args"] == {"a": 5, "b": 3}

    def test_normalize_skips_invalid_arguments_and_reports(self):
        events = []
        agent = make_agent()
        agent.event_callback = events.append

        calls = agent._normalize_native_tool_calls([
            {"id": "call_1", "name": "add", "arguments": 'not-json {{'},
        ])

        assert calls == []
        assert any("invalid JSON arguments" in event for event in events)


class TestNativeToolCallWorkflow:
    def _make_fake_create(self, streams, captured_kwargs):
        stream_queue = list(streams)

        async def fake_create(**kwargs):
            captured_kwargs.append(kwargs)
            if isinstance(stream_queue[0], Exception):
                raise stream_queue.pop(0)
            return stream_queue.pop(0)

        return fake_create

    @pytest.mark.asyncio
    async def test_full_native_flow_preserves_ids_and_attaches_results(self):
        agent = make_agent()
        register_add_tool(agent)

        first_stream = FakeStream([
            content_chunk("I will add the numbers."),
            tool_call_delta(index=0, id="call_100", name="add"),
            tool_call_delta(index=0, arguments='{"a": 5, "b": 3}'),
            make_chunk(finish_reason="tool_calls"),
        ])
        second_stream = FakeStream([content_chunk("The answer is 8")])

        captured = []
        agent.client.chat.completions.create = self._make_fake_create(
            [first_stream, second_stream], captured
        )

        response = await agent.get_ai_response("What is 5+3?")

        assert response == "The answer is 8"

        # Native tools were passed through the `tools` parameter.
        assert "tools" in captured[0]
        assert any(
            schema["function"]["name"] == "add" for schema in captured[0]["tools"]
        )

        # Assistant turn preserved the native tool-call ID.
        assistant_message = next(
            m for m in agent.conversation_history if m.get("tool_calls")
        )
        assert assistant_message["role"] == "assistant"
        call_entry = assistant_message["tool_calls"][0]
        assert call_entry["id"] == "call_100"
        assert call_entry["type"] == "function"
        assert call_entry["function"]["name"] == "add"

        # Tool result attached to the same ID via role="tool".
        tool_message = next(m for m in agent.conversation_history if m["role"] == "tool")
        assert tool_message["tool_call_id"] == "call_100"
        payload = json.loads(tool_message["content"])
        assert payload["success"] is True
        assert payload["result"] == "8"

        # The follow-up request replayed the native messages.
        followup_messages = captured[1]["messages"]
        roles_with_ids = [
            m for m in followup_messages
            if m["role"] == "tool" and m.get("tool_call_id") == "call_100"
        ]
        assert roles_with_ids, "tool result missing from follow-up request"

    @pytest.mark.asyncio
    async def test_unsupported_backend_downgrades_to_fallback_parser(self):
        agent = make_agent(backend="ollama")
        register_add_tool(agent)
        events = []
        agent.event_callback = events.append

        error = openai.BadRequestError(
            "tools parameter is not supported by this server",
            response=SimpleNamespace(
                status_code=400,
                request=SimpleNamespace(method="POST", url="http://test/v1/chat/completions", headers={}),
                headers={},
            ),
            body=None,
        )
        fallback_stream = FakeStream([
            content_chunk('{"tool_calls":[{"tool":"add","args":{"a":5,"b":3}}]}'),
        ])
        final_stream = FakeStream([content_chunk("The answer is 8")])

        captured = []
        agent.client.chat.completions.create = self._make_fake_create(
            [error, fallback_stream, final_stream], captured
        )

        response = await agent.get_ai_response("What is 5+3?")

        assert response == "The answer is 8"
        assert agent._use_native_tools() is False
        assert any("fallback" in event.lower() for event in events)

        # Retry happened without the tools parameter.
        assert "tools" not in captured[1]

        # The JSON payload was executed through the shared execution path.
        assert any(
            m["role"] == "user" and '"result": "8"' in m.get("content", "")
            for m in agent.conversation_history
        )

    @pytest.mark.asyncio
    async def test_no_registered_tools_omits_tools_parameter(self):
        agent = make_agent()
        agent.tool_manager = AsyncToolManager(tools_directory="/nonexistent-scout-test-tools")
        stream = FakeStream([content_chunk("Plain answer")])

        captured = []
        agent.client.chat.completions.create = self._make_fake_create([stream], captured)

        response = await agent.get_ai_response("Hi")

        assert response == "Plain answer"
        assert "tools" not in captured[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
