"""
Integration tests for Scout AI Assistant.

Tests cover:
- Agent initialization and configuration
- Tool manager discovery and registration
- Tool execution workflows
- Agent response generation with tool calls
- Error handling and edge cases
"""

import asyncio
import json
import pytest
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from agent import AsyncAIAgent
from tool_manager import AsyncToolManager, ToolSpec
from config import get_llm_config


class TestToolManagerIntegration:
    """Integration tests for AsyncToolManager."""

    def test_tool_manager_initialization(self):
        """Test that tool manager initializes correctly."""
        manager = AsyncToolManager()
        assert manager.tools_directory == "tools"
        assert len(manager.tools) == 0
        assert not manager._loaded

    def test_tool_registration(self):
        """Test registering a tool with the manager."""
        manager = AsyncToolManager()
        
        def test_handler(text: str) -> str:
            return f"Echo: {text}"
        
        tool_def = {
            "name": "echo",
            "description": "Echo back text",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"}
                },
                "required": ["text"]
            },
            "handler": test_handler,
            "risk": "low"
        }
        
        manager.register(tool_def)
        
        assert "echo" in manager.tools
        assert manager.tools["echo"].name == "echo"
        assert manager.tools["echo"].description == "Echo back text"
        assert manager.tools["echo"].risk == "low"

    def test_tool_registration_with_aliases(self):
        """Test registering a tool with aliases."""
        manager = AsyncToolManager()
        
        def test_handler() -> str:
            return "test"
        
        tool_def = {
            "name": "test_tool",
            "description": "Test tool",
            "parameters": {},
            "handler": test_handler,
            "aliases": ["t", "tt"]
        }
        
        manager.register(tool_def)
        
        assert manager.resolve_tool_name("t") == "test_tool"
        assert manager.resolve_tool_name("tt") == "test_tool"
        assert manager.resolve_tool_name("test_tool") == "test_tool"

    def test_tool_registration_validation(self):
        """Test tool registration validation."""
        manager = AsyncToolManager()
        
        # Test missing handler
        with pytest.raises(TypeError):
            manager.register({
                "name": "bad_tool",
                "description": "Bad tool",
                "parameters": {},
                "handler": None  # Not callable
            })
        
        # Test empty name
        with pytest.raises(ValueError):
            manager.register({
                "name": "",
                "description": "Bad tool",
                "parameters": {},
                "handler": lambda: None
            })

    @pytest.mark.asyncio
    async def test_execute_sync_tool(self):
        """Test executing a synchronous tool."""
        manager = AsyncToolManager()
        
        def add(a: int, b: int) -> int:
            return a + b
        
        tool_def = {
            "name": "add",
            "description": "Add two numbers",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"}
                },
                "required": ["a", "b"]
            },
            "handler": add
        }
        
        manager.register(tool_def)
        
        result = await manager.execute_tool_call("add", {"a": 5, "b": 3})
        
        assert result["success"] is True
        assert result["result"] == "8"
        assert result["tool"] == "add"

    @pytest.mark.asyncio
    async def test_execute_async_tool(self):
        """Test executing an asynchronous tool."""
        manager = AsyncToolManager()
        
        async def async_greet(name: str) -> str:
            await asyncio.sleep(0.01)  # Simulate async work
            return f"Hello, {name}!"
        
        tool_def = {
            "name": "greet",
            "description": "Greet someone",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"}
                },
                "required": ["name"]
            },
            "handler": async_greet
        }
        
        manager.register(tool_def)
        
        result = await manager.execute_tool_call("greet", {"name": "World"})
        
        assert result["success"] is True
        assert "Hello, World!" in result["result"]

    @pytest.mark.asyncio
    async def test_tool_execution_error_handling(self):
        """Test tool execution error handling."""
        manager = AsyncToolManager()
        
        def failing_tool() -> None:
            raise RuntimeError("Tool failed intentionally")
        
        tool_def = {
            "name": "fail",
            "description": "Failing tool",
            "parameters": {},
            "handler": failing_tool,
            "risk": "high"
        }
        
        manager.register(tool_def)
        
        result = await manager.execute_tool_call("fail", {})
        
        assert result["success"] is False
        assert "Tool failed intentionally" in result["result"]
        assert "error" in result

    @pytest.mark.asyncio
    async def test_tool_not_found(self):
        """Test executing a non-existent tool."""
        manager = AsyncToolManager()
        
        with pytest.raises(ValueError, match="not found"):
            await manager.execute_tool_call("non_existent", {})

    def test_tool_argument_coercion(self):
        """Test argument type coercion."""
        manager = AsyncToolManager()
        
        def typed_func(text: str, count: int, ratio: float) -> str:
            return f"{text} {count} {ratio}"
        
        tool_def = {
            "name": "typed",
            "description": "Typed function",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "count": {"type": "integer"},
                    "ratio": {"type": "number"}
                },
                "required": ["text", "count", "ratio"]
            },
            "handler": typed_func
        }
        
        manager.register(tool_def)
        spec = manager.tools["typed"]
        
        # Test valid coercion
        coerced = manager._coerce_args(spec, {"text": "hello", "count": 5, "ratio": 3.14})
        assert coerced["text"] == "hello"
        assert coerced["count"] == 5
        assert coerced["ratio"] == 3.14
        
        # Test string to integer coercion
        coerced = manager._coerce_args(spec, {"text": "hello", "count": "10", "ratio": "2.5"})
        assert coerced["count"] == 10
        assert coerced["ratio"] == 2.5

    def test_describe_tools(self):
        """Test tool description generation."""
        manager = AsyncToolManager()
        
        tool_def = {
            "name": "test",
            "description": "Test tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "arg": {"type": "string"}
                }
            },
            "handler": lambda arg: arg,
            "risk": "medium"
        }
        
        manager.register(tool_def)
        descriptions = manager.describe_tools()
        
        assert len(descriptions) == 1
        assert descriptions[0]["name"] == "test"
        assert descriptions[0]["description"] == "Test tool"
        assert descriptions[0]["risk"] == "medium"


class TestAsyncAIAgentIntegration:
    """Integration tests for AsyncAIAgent."""

    @pytest.mark.asyncio
    async def test_agent_initialization(self):
        """Test agent initializes with valid configuration."""
        with patch('config.get_llm_config') as mock_config:
            mock_config.return_value = {
                "api_key": "test-key",
                "backend": "openai",
                "model": "gpt-4",
                "base_url": "https://api.openai.com/v1"
            }
            
            agent = AsyncAIAgent()
            
            assert agent.backend == "openai"
            assert agent.model == "gpt-4"
            assert agent.max_iterations == 10
            assert len(agent.conversation_history) == 0

    @pytest.mark.asyncio
    async def test_agent_initialization_no_api_key(self):
        """Test agent raises error when API key is missing."""
        with patch('config.get_llm_config') as mock_config:
            mock_config.return_value = {
                "api_key": None,
                "backend": "openai",
                "model": "gpt-4",
                "base_url": "https://api.openai.com/v1"
            }
            
            with pytest.raises(RuntimeError, match="API key is not set"):
                AsyncAIAgent()

    @pytest.mark.asyncio
    async def test_parse_tool_calls_json_format(self):
        """Test parsing tool calls from JSON response."""
        with patch('config.get_llm_config') as mock_config:
            mock_config.return_value = {
                "api_key": "test-key",
                "backend": "openai",
                "model": "gpt-4",
                "base_url": "https://api.openai.com/v1"
            }
            
            agent = AsyncAIAgent()
            
            # Test valid JSON with tool_calls array
            response = '{"tool_calls":[{"tool":"echo","args":{"text":"hello"}}]}'
            tool_calls = agent._parse_tool_calls(response)
            
            assert len(tool_calls) == 1
            assert tool_calls[0]["tool"] == "echo"
            assert tool_calls[0]["args"]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_parse_tool_calls_markdown_format(self):
        """Test parsing tool calls from markdown-wrapped JSON."""
        with patch('config.get_llm_config') as mock_config:
            mock_config.return_value = {
                "api_key": "test-key",
                "backend": "openai",
                "model": "gpt-4",
                "base_url": "https://api.openai.com/v1"
            }
            
            agent = AsyncAIAgent()
            
            # Test markdown-wrapped JSON
            response = '''Some text here
```json
{"tool_calls":[{"tool":"test","args":{}}]}
```
More text'''
            tool_calls = agent._parse_tool_calls(response)
            
            assert len(tool_calls) == 1
            assert tool_calls[0]["tool"] == "test"

    @pytest.mark.asyncio
    async def test_parse_tool_calls_single_call(self):
        """Test parsing single tool call (not in array)."""
        with patch('config.get_llm_config') as mock_config:
            mock_config.return_value = {
                "api_key": "test-key",
                "backend": "openai",
                "model": "gpt-4",
                "base_url": "https://api.openai.com/v1"
            }
            
            agent = AsyncAIAgent()
            
            # Single tool call object
            response = '{"tool":"echo","args":{"text":"hello"}}'
            tool_calls = agent._parse_tool_calls(response)
            
            assert len(tool_calls) == 1
            assert tool_calls[0]["tool"] == "echo"

    @pytest.mark.asyncio
    async def test_parse_tool_calls_no_tools(self):
        """Test parsing response with no tool calls."""
        with patch('config.get_llm_config') as mock_config:
            mock_config.return_value = {
                "api_key": "test-key",
                "backend": "openai",
                "model": "gpt-4",
                "base_url": "https://api.openai.com/v1"
            }
            
            agent = AsyncAIAgent()
            
            # Response without tool calls
            response = "This is just a plain text response"
            tool_calls = agent._parse_tool_calls(response)
            
            assert len(tool_calls) == 0

    @pytest.mark.asyncio
    async def test_conversation_history_management(self):
        """Test conversation history is properly maintained."""
        with patch('config.get_llm_config') as mock_config:
            mock_config.return_value = {
                "api_key": "test-key",
                "backend": "openai",
                "model": "gpt-4",
                "base_url": "https://api.openai.com/v1"
            }
            
            agent = AsyncAIAgent()
            
            agent._add_message("user", "Hello")
            agent._add_message("assistant", "Hi there")
            
            assert len(agent.conversation_history) == 2
            assert agent.conversation_history[0]["role"] == "user"
            assert agent.conversation_history[0]["content"] == "Hello"
            assert agent.conversation_history[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_conversation_history_truncation(self):
        """Test conversation history is truncated when exceeding max."""
        with patch('config.get_llm_config') as mock_config:
            mock_config.return_value = {
                "api_key": "test-key",
                "backend": "openai",
                "model": "gpt-4",
                "base_url": "https://api.openai.com/v1"
            }
            
            agent = AsyncAIAgent()
            agent.max_history_messages = 5
            
            # Add more messages than max
            for i in range(10):
                agent._add_message("user", f"Message {i}")
            
            # Should only keep last 5
            assert len(agent.conversation_history) == 5
            assert "Message 5" in agent.conversation_history[0]["content"]
            assert "Message 9" in agent.conversation_history[-1]["content"]

    @pytest.mark.asyncio
    async def test_conversation_history_is_summarized_before_trim(self):
        """Summarization receives the complete history before older turns are removed."""
        with patch('config.get_llm_config') as mock_config:
            mock_config.return_value = {
                "api_key": "test-key",
                "backend": "openai",
                "model": "gpt-4",
                "base_url": "https://api.openai.com/v1",
            }

            agent = AsyncAIAgent()
            agent.max_history_messages = 5
            original_messages = [
                {"role": "user", "content": f"Message {index}"}
                for index in range(7)
            ]
            agent.conversation_history = list(original_messages)
            agent.summarize_conversation = AsyncMock(return_value="Summary of messages 0 through 6")

            await agent._compact_history_if_needed()

            agent.summarize_conversation.assert_awaited_once_with(original_messages)
            assert agent._conversation_summary == "Summary of messages 0 through 6"
            assert agent.conversation_history == original_messages[-4:]
            assert len(agent.conversation_history) == 4

    @pytest.mark.asyncio
    async def test_event_callback(self):
        """Test event callback is properly invoked."""
        with patch('config.get_llm_config') as mock_config:
            mock_config.return_value = {
                "api_key": "test-key",
                "backend": "openai",
                "model": "gpt-4",
                "base_url": "https://api.openai.com/v1"
            }
            
            events = []
            callback = lambda msg: events.append(msg)
            
            agent = AsyncAIAgent(event_callback=callback)
            agent._emit_event("Test event")
            
            assert len(events) == 1
            assert events[0] == "Test event"

    @pytest.mark.asyncio
    async def test_get_ai_response_direct_answer(self):
        """Test agent returning direct answer without tool calls."""
        with patch('config.get_llm_config') as mock_config:
            mock_config.return_value = {
                "api_key": "test-key",
                "backend": "openai",
                "model": "gpt-4",
                "base_url": "https://api.openai.com/v1"
            }
            
            agent = AsyncAIAgent()
            
            # Mock the AI decision to return plain text
            with patch.object(agent, '_get_ai_decision') as mock_decision:
                mock_decision.return_value = "This is a direct answer"
                
                response = await agent.get_ai_response("What is 2+2?")
                
                assert response == "This is a direct answer"
                assert len(agent.conversation_history) == 2

    @pytest.mark.asyncio
    async def test_get_ai_response_with_tool_calls(self):
        """Test agent workflow with tool execution."""
        with patch('config.get_llm_config') as mock_config:
            mock_config.return_value = {
                "api_key": "test-key",
                "backend": "openai",
                "model": "gpt-4",
                "base_url": "https://api.openai.com/v1"
            }
            
            agent = AsyncAIAgent()
            
            # Register a test tool
            def add(a: int, b: int) -> int:
                return a + b
            
            tool_def = {
                "name": "add",
                "description": "Add numbers",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "integer"},
                        "b": {"type": "integer"}
                    },
                    "required": ["a", "b"]
                },
                "handler": add
            }
            
            agent.tool_manager.register(tool_def)
            
            # Mock AI to first call tool, then return final answer
            responses = [
                '{"tool_calls":[{"tool":"add","args":{"a":5,"b":3}}]}',
                "The answer is 8"
            ]
            
            with patch.object(agent, '_get_ai_decision') as mock_decision:
                mock_decision.side_effect = responses
                
                response = await agent.get_ai_response("What is 5+3?")
                
                assert "8" in response
                assert len(agent.conversation_history) > 2

    @pytest.mark.asyncio
    async def test_failed_tool_recovery_context_is_injected(self):
        """Test failed tool results add a recovery instruction to the next model turn."""
        with patch('config.get_llm_config') as mock_config:
            mock_config.return_value = {
                "api_key": "test-key",
                "backend": "openai",
                "model": "gpt-4",
                "base_url": "https://api.openai.com/v1"
            }

            agent = AsyncAIAgent()
            agent._tool_recovery_context = "Recovery instruction: retry safely."

            captured = {}

            async def fake_create(**kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="final answer"))]
                )

            agent.client.chat.completions.create = fake_create

            response = await agent._get_ai_decision()

            assert response == "final answer"
            messages = captured["messages"]
            assert messages[0]["role"] == "system"
            assert any(
                message["role"] == "system" and "Recovery instruction" in message["content"]
                for message in messages
            )

    @pytest.mark.asyncio
    async def test_max_iterations_limit(self):
        """Test agent respects max iterations limit."""
        with patch('config.get_llm_config') as mock_config:
            mock_config.return_value = {
                "api_key": "test-key",
                "backend": "openai",
                "model": "gpt-4",
                "base_url": "https://api.openai.com/v1"
            }
            
            agent = AsyncAIAgent()
            agent.max_iterations = 2
            
            # Mock AI to always return tool calls (infinite loop scenario)
            with patch.object(agent, '_get_ai_decision') as mock_decision:
                mock_decision.return_value = '{"tool_calls":[{"tool":"test","args":{}}]}'
                
                with patch.object(agent, '_execute_tools_and_wait') as mock_exec:
                    mock_exec.return_value = [{"tool": "test", "success": True, "result": "ok"}]
                    
                    response = await agent.get_ai_response("Test")
                    
                    # Should stop after max_iterations
                    assert "thinking limit" in response.lower()


class TestEndToEndWorkflow:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    async def test_simple_math_workflow(self):
        """Test complete workflow: user query -> tool execution -> response."""
        with patch('config.get_llm_config') as mock_config:
            mock_config.return_value = {
                "api_key": "test-key",
                "backend": "openai",
                "model": "gpt-4",
                "base_url": "https://api.openai.com/v1"
            }
            
            agent = AsyncAIAgent()
            
            # Register a simple math tool
            def multiply(x: int, y: int) -> int:
                return x * y
            
            agent.tool_manager.register({
                "name": "multiply",
                "description": "Multiply two numbers",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"}
                    },
                    "required": ["x", "y"]
                },
                "handler": multiply
            })
            
            # Simulate the workflow
            responses = [
                '{"tool_calls":[{"tool":"multiply","args":{"x":6,"y":7}}]}',
                "The product of 6 and 7 is 42"
            ]
            
            with patch.object(agent, '_get_ai_decision') as mock_decision:
                mock_decision.side_effect = responses
                
                result = await agent.get_ai_response("What is 6 times 7?")
                
                assert "42" in result
                # Verify conversation history was maintained
                assert len(agent.conversation_history) >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
