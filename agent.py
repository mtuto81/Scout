import asyncio
import platform
import openai
from openai import AsyncOpenAI
from config import get_llm_config
from tool_manager import AsyncToolManager
from logger import Logger
import json
import re
from typing import Callable, Dict, List, Any, Optional


class AsyncAIAgent:
    def __init__(
        self,
        event_callback: Optional[Callable[[str], None]] = None,
        stream_callback: Optional[Callable[[str], None]] = None,
    ):
        llm_config = get_llm_config()
        if not llm_config["api_key"]:
            raise RuntimeError(f"API key is not set for backend '{llm_config['backend']}'.")

        self.backend = llm_config["backend"]
        self.model = llm_config["model"]
        self.base_url = llm_config["base_url"]
        self.client = AsyncOpenAI(base_url=self.base_url, api_key=llm_config["api_key"])
        self.tool_manager = AsyncToolManager()
        self.logger = Logger()
        self.event_callback = event_callback
        self.stream_callback = stream_callback
        self.conversation_history: List[Dict[str, Any]] = []
        self.max_iterations = 40
        self.max_history_messages = 20
        self.max_parse_repairs = 1
        self._tool_recovery_context: str = ""
        self._emitted_tool_load_errors: set[str] = set()
        self._conversation_summary: str = ""

    async def get_ai_response(self, prompt: str) -> str:
        self._add_message("user", prompt)
        try:
            self.logger.log({"user_prompt": prompt})
        except Exception:
            pass

        tool_results = []
        for iteration in range(self.max_iterations):
            await self._compact_history_if_needed()
            self._emit_event(f"Agent thinking...")
            ai_response = await self._get_ai_decision()
        
            tool_calls = await self._parse_tool_calls(ai_response)
            if not tool_calls:
                self._add_message("assistant", ai_response)
                self._tool_recovery_context = ""
                try:
                    self.logger.log({"final_response": ai_response})
                except Exception:
                    pass
                return ai_response

            # Emit the AI's reasoning before the tool call JSON
            reasoning = self._extract_reasoning(ai_response)
            if reasoning:
                self._emit_event(reasoning)

            self._emit_event(f"Executing {len(tool_calls)} tool(s)...")
            tool_results = await self._execute_tools_and_wait(tool_calls)
            self._add_tool_results_to_history(tool_calls, tool_results)

        fallback_response = "Error: Maximum iterations reached without a final answer. Last tool results:\n" + json.dumps(tool_results, ensure_ascii=False, indent=2)
        self._add_message("assistant", fallback_response)
        self._tool_recovery_context = ""
        return fallback_response

    async def _compact_history_if_needed(self) -> None:
        """Summarize old turns before the model context becomes unnecessarily large."""
        limit = self.max_history_messages
        if limit <= 0 or len(self.conversation_history) <= limit:
            return

        full_history = list(self.conversation_history)
        keep_count = max(4, limit // 2)
        recent_messages = full_history[-keep_count:]
        self._emit_event("Conversation context is large. Summarizing older messages...")

        try:
            summary = await self.summarize_conversation(full_history)
        except Exception as exc:
            self._emit_event(f"Conversation summary failed; trimming older messages: {exc}")
            self.conversation_history = recent_messages
            return

        self._conversation_summary = summary
        self.conversation_history = recent_messages
        self._emit_event("Older conversation messages summarized.")

    async def summarize_conversation(self, messages: List[Dict[str, Any]]) -> str:
        """Return a concise summary without changing the agent's chat history."""
        conversation = self._format_conversation_for_prompt(messages)
        if not conversation:
            return "No conversation to summarize."

        prompt = (
            "Summarize the following Scout conversation for future reference. "
            "Represent the important request, actions taken, tool results, failures, "
            "and unresolved tasks. Be concise and factual. Do not invent details. "
            "Return only the summary, with no preamble.\n\n"
            f"{conversation}"
        )
        return await self._request_text(prompt)

    async def generate_conversation_title(self, messages: List[Dict[str, Any]]) -> str:
        """Generate a short title without changing the agent's chat history."""
        conversation = self._format_conversation_for_prompt(messages)
        if not conversation:
            return "New chat"

        prompt = (
            "Create a short descriptive title for the following conversation. "
            "Use 3 to 8 words, do not use quotation marks, and return only the title. "
            "Focus on the user's main goal.\n\n"
            f"{conversation}"
        )
        title = await self._request_text(prompt)
        title = " ".join(title.split()).strip(" \t\r\n\"'")
        return title[:80] or "New chat"

    def _format_conversation_for_prompt(self, messages: List[Dict[str, Any]]) -> str:
        """Format every valid message so every conversation turn is represented."""
        lines = []
        for index, message in enumerate(messages or [], start=1):
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", "unknown")).strip().lower() or "unknown"
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            lines.append(f"Message {index} ({role}):\n{content.strip()}")
        return "\n\n".join(lines)

    async def _request_text(self, prompt: str) -> str:
        """Make a one-shot metadata request without mutating conversation history."""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a careful conversation metadata assistant."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )
        except openai.AuthenticationError:
            raise RuntimeError(
                f"Authentication failed for backend '{self.backend}'. Check your API key in Settings."
            )
        except openai.RateLimitError:
            raise RuntimeError(
                f"Rate limit exceeded for backend '{self.backend}'. Wait a moment and try again."
            )
        except openai.APITimeoutError:
            raise RuntimeError(
                f"Request timed out for backend '{self.backend}'. Check your network connection."
            )
        except openai.APIConnectionError:
            raise RuntimeError(
                f"Cannot connect to backend '{self.backend}'. Check your network connection and backend URL in Settings."
            )
        except openai.APIError as exc:
            raise RuntimeError(f"Backend '{self.backend}' returned an error: {exc}")

        content = response.choices[0].message.content
        return content.strip() if isinstance(content, str) else ""

    async def _get_ai_decision(self) -> str:
        tool_schemas = json.dumps(self.tool_manager.describe_tools(), ensure_ascii=False, indent=2)
        self._emit_tool_load_errors()

        system_prompt = f"""
You are Scout, a highly capable IT AI assistant with access to tools. You solve user requests by reasoning step-by-step and calling tools when needed.
The assistant is running on a {platform.system()} machine.

## Your Capabilities:
- Think step by step before acting.
- Explain your reasoning when you decide to call tools.
- Make a plan if multiple steps or tools are needed, explain it to the  user and execute them iteratively.
- You may call one or more tools per step.

- Ask the user before high-risk actions unless the tool itself asks for confirmation.
- Always return results to the user, integrating tool outputs into a final answer.
Never trust the tool's claim of success; verify the resulting state.
## Available Tools
{tool_schemas}

## Response Rules:
1. If you can answer directly, do so without calling tools.
2. It you need tools, explain your reasoning and which tools you will call before calling them.
3. If you need tools, respond ONLY with this JSON object and no markdown:
{{"tool_calls":[{{"tool":"tool_name","args":{{"arg_name":"value"}}}}]}}
4. Use object-style args that match the tool schema. Use {{}} for tools with no arguments.
5. After receiving tool results, summarize them and conclude.
6. Do not claim a tool succeeded unless the tool result says success is true.
Never trust the tool's claim of success; verify the resulting state.

"""

        messages = [{"role": "system", "content": system_prompt}]
        if self._conversation_summary:
            messages.append({
                "role": "system",
                "content": "Summary of earlier conversation messages:\n" + self._conversation_summary,
            })
        if self._tool_recovery_context:
            messages.append({"role": "system", "content": self._tool_recovery_context})
        messages.extend(self.conversation_history)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                stream=True,
            )
            return await self._collect_streamed_response(response)
        except openai.AuthenticationError:
            raise RuntimeError(
                f"Authentication failed for backend '{self.backend}'. Check your API key in Settings."
            )
        except openai.RateLimitError:
            raise RuntimeError(
                f"Rate limit exceeded for backend '{self.backend}'. Wait a moment and try again."
            )
        except openai.APITimeoutError:
            raise RuntimeError(
                f"Request timed out for backend '{self.backend}'. Check your network connection."
            )
        except openai.APIConnectionError:
            if self.backend == "local":
                raise RuntimeError(
                    "Cannot connect to the local backend. It may have been stopped due to inactivity. "
                    "Try submitting your query again to restart it."
                )
            raise RuntimeError(
                f"Cannot connect to backend '{self.backend}'. Check your network connection and backend URL in Settings."
            )
        except openai.APIError as e:
            raise RuntimeError(
                f"Backend '{self.backend}' returned an error: {e}"
            )

        return response.choices[0].message.content

    async def _collect_streamed_response(self, stream) -> str:
        final_parts = []
        visible_parts = []

        async for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            reasoning = (
                getattr(delta, "reasoning_content", None)
                or getattr(delta, "reasoning", None)
            )
            content = getattr(delta, "content", None)

            if reasoning:
                visible_parts.append(reasoning)
            if content:
                final_parts.append(content)
                visible_parts.append(content)

            if reasoning or content:
                self._emit_stream("".join(visible_parts))

        return "".join(final_parts or visible_parts).strip()

    def _emit_stream(self, content: str) -> None:
        if self.stream_callback:
            self.stream_callback(content)

    def _emit_tool_load_errors(self) -> None:
        for error in self.tool_manager.get_load_errors():
            if error in self._emitted_tool_load_errors:
                continue
            self._emitted_tool_load_errors.add(error)
            self._emit_event(f"Tool loading warning: {error}")


    async def _repair_tool_json(self, raw_response: str, error: str) -> str: 
        repair_prompt = f"""
            The previous response contained invalid tool call JSON.

            Error:
            {error}

            Raw output:
            {raw_response}

            Return ONLY valid JSON in this format:
            {{
            "tool_calls": [
                {{
                "tool": "tool_name",
                "args": {{}}
                }}
            ]
            }}
          """
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": repair_prompt}],
            temperature=0.0
        )
        return response.choices[0].message.content


    async def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        parse_errors = []
        saw_tool_payload = False
        
        # First attempt: parse raw response
        for candidate in self._json_candidates(response.strip()):
            parsed = self._loads_json_candidate(candidate)
            if parsed is None:
                continue

            tool_calls, errors, saw_payload = self._tool_calls_from_parsed(parsed)
            saw_tool_payload = saw_tool_payload or saw_payload
            if tool_calls:
                return tool_calls
            parse_errors.extend(errors)

        # Second attempt: if it looks like a tool call but failed, try LLM repair
        if self._looks_like_tool_payload(response):
            saw_tool_payload = True
            error_msg = "; ".join(parse_errors) if parse_errors else "Invalid JSON structure"
            repaired_response = await self._repair_tool_json(response, error_msg)
            
            for candidate in self._json_candidates(repaired_response.strip()):
                parsed = self._loads_json_candidate(candidate)
                if parsed is None:
                    continue
                tool_calls, errors, saw_payload = self._tool_calls_from_parsed(parsed)
                if tool_calls:
                    return tool_calls
                parse_errors.extend(errors)

        if saw_tool_payload:
            if parse_errors:
                self._emit_tool_parse_errors(parse_errors)
            else:
                self._emit_event("Tool call ignored: the model returned invalid JSON.")
        return []

    def _tool_calls_from_parsed(self, parsed: Any) -> tuple[List[Dict[str, Any]], List[str], bool]:
        errors = []
        saw_payload = False
        if isinstance(parsed, dict) and "tool_calls" in parsed:
            saw_payload = True
            parsed = parsed["tool_calls"]

        if isinstance(parsed, dict) and "tool" in parsed:
            saw_payload = True
            call = self._validate_tool_call(parsed, 1, errors)
            if call:
                return [call], errors, saw_payload
            return [], errors, saw_payload

        if isinstance(parsed, list):
            valid_calls = []
            for index, call in enumerate(parsed, start=1):
                call = self._validate_tool_call(call, index, errors)
                if call:
                    valid_calls.append(call)
            if valid_calls:
                saw_payload = True
            return valid_calls, errors, saw_payload

        if saw_payload:
            errors.append("tool_calls must be a list of tool call objects")
        return [], errors, saw_payload

    def _json_candidates(self, text: str) -> List[str]:
        candidates = [text]

        fence_pattern = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
        candidates.extend(match.group(1).strip() for match in fence_pattern.finditer(text))

        candidates.extend(self._balanced_json_snippets(text))

        seen = set()
        unique_candidates = []
        for candidate in candidates:
            candidate = candidate.strip()
            if candidate and candidate not in seen:
                seen.add(candidate)
                unique_candidates.append(candidate)
        return unique_candidates

    def _balanced_json_snippets(self, text: str) -> List[str]:
        snippets = []
        for start, char in enumerate(text):
            if char not in "{[":
                continue

            expected_stack = ["}" if char == "{" else "]"]
            in_string = False
            escaped = False

            for index in range(start + 1, len(text)):
                current = text[index]
                if in_string:
                    if escaped:
                        escaped = False
                    elif current == "\\":
                        escaped = True
                    elif current == '"':
                        in_string = False
                    continue

                if current == '"':
                    in_string = True
                elif current in "{[":
                    expected_stack.append("}" if current == "{" else "]")
                elif current in "}]":
                    if not expected_stack or current != expected_stack[-1]:
                        break
                    expected_stack.pop()
                    if not expected_stack:
                        snippets.append(text[start:index + 1])
                        break
        return snippets

    def _loads_json_candidate(self, candidate: str) -> Any:
        for repaired_candidate in self._json_repair_candidates(candidate):
            try:
                return json.loads(repaired_candidate)
            except json.JSONDecodeError:
                pass
        return None

    def _json_repair_candidates(self, candidate: str) -> List[str]:
        candidates = [candidate]

        without_trailing_commas = re.sub(r",\s*([}\]])", r"\1", candidate)
        candidates.append(without_trailing_commas)

        # Small, schema-focused repairs for common LLM JSON mistakes:
        #   {tool": "..."}  -> {"tool": "..."}
        #   {tool: "..."}   -> {"tool": "..."}
        repaired_keys = without_trailing_commas
        for key in ("tool_calls", "tool", "args", "command", "require_confirm", "timeout_seconds"):
            repaired_keys = re.sub(
                rf'([{{\[,]\s*){re.escape(key)}"\s*:',
                rf'\1"{key}":',
                repaired_keys,
            )
            repaired_keys = re.sub(
                rf'([{{\[,]\s*){re.escape(key)}\s*:',
                rf'\1"{key}":',
                repaired_keys,
            )
        candidates.append(repaired_keys)

        seen = set()
        unique_candidates = []
        for item in candidates:
            if item not in seen:
                seen.add(item)
                unique_candidates.append(item)
        return unique_candidates

    def _validate_tool_call(self, call: Any, index: int, errors: List[str]) -> Optional[Dict[str, Any]]:
        if not isinstance(call, dict):
            errors.append(f"tool call {index} is not an object")
            return None

        tool_name = call.get("tool")
        if not isinstance(tool_name, str) or not tool_name.strip():
            errors.append(f"tool call {index} has no valid tool name")
            return None

        args = call.get("args", {})
        if args is None:
            args = {}
        if not isinstance(args, dict):
            errors.append(f"tool call {index} args must be an object")
            return None

        return {"tool": tool_name.strip(), "args": args}

    def _looks_like_tool_payload(self, response: str) -> bool:
        lowered = response.lower()
        return "tool_calls" in lowered or '"tool"' in lowered or "'tool'" in lowered

    def _emit_tool_parse_errors(self, errors: List[str]) -> None:
        if errors:
            self._emit_event("Tool call ignored: " + "; ".join(errors) + ".")

    async def _execute_tools_and_wait(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tasks = []
        for i, call in enumerate(tool_calls):
            tool_name = call.get("tool")
            tool_args = call.get("args", {})
            self._emit_event(f"Starting tool {i + 1}: {tool_name}")
            tasks.append(asyncio.create_task(self._execute_single_tool(tool_name, tool_args, i + 1)))

        self._emit_event("Waiting for all tools to complete...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                processed.append({
                    "tool": tool_calls[i].get("tool"),
                    "success": False,
                    "result": f"Tool execution failed: {str(res)}",
                    "error": str(res),
                })
                self._emit_event(f"Tool {i + 1} failed: {res}")
            else:
                processed.append(res)
                self._emit_event(f"Tool {i + 1} completed")

        return processed

    async def _execute_single_tool(self, tool_name: str, args: Any, tool_index: int) -> Dict[str, Any]:
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                result = await self.tool_manager.execute_tool_call(tool_name, args)

                if result.get("success", False):
                    return result

                last_error = result.get("error") or result.get("result")

            except Exception as e:
                last_error = str(e)

            # 🔁 small backoff
            await asyncio.sleep(0.3 * (attempt + 1))

        return {
            "tool": tool_name,
            "args": args,
            "success": False,
            "result": last_error,
            "error": last_error,
            "retried": True
        }


    def _add_tool_results_to_history(self, tool_calls: List[Dict[str, Any]], tool_results: List[Dict[str, Any]]):
        self._add_message("assistant", json.dumps({"tool_calls": tool_calls}, ensure_ascii=False))
        failed_tools = [result for result in tool_results if not result.get("success", False)]
        self._tool_recovery_context = self._build_recovery_context(tool_calls, tool_results) if failed_tools else ""
        self._add_message(
            "user",
            "Tool results:\n" + json.dumps(tool_results, ensure_ascii=False, indent=2),
        )
        if failed_tools:
            self._emit_event("Tool failure detected. Recovery guidance added to the next model turn.")

    def _build_recovery_context(self, tool_calls: List[Dict[str, Any]], tool_results: List[Dict[str, Any]]) -> str:
        failed_entries = []
        for call, result in zip(tool_calls, tool_results):
            if result.get("success", False):
                continue
            failed_entries.append(
                {
                    "tool": call.get("tool"),
                    "args": call.get("args", {}),
                    "error": result.get("error") or result.get("result") or "Unknown error",
                }
            )

        if not failed_entries:
            return ""

        return (
            "Recovery instruction:\n"
            "One or more tools failed. Retry the task with a corrected or safer tool call, or ask the user for missing information if needed. "
            "Do not finalize with only the failure unless the task is impossible or unsafe.\n"
            "Failed tool details:\n"
            + json.dumps(failed_entries, ensure_ascii=False, indent=2)
        )

    def _add_message(self, role: str, content: str) -> None:
        self.conversation_history.append({"role": role, "content": content})
        if self.max_history_messages > 0 and len(self.conversation_history) > self.max_history_messages:
            self.conversation_history = self.conversation_history[-self.max_history_messages:]

    def _emit_event(self, message: str) -> None:
        if self.event_callback:
            self.event_callback(message)
        else:
            print(message)

    def _extract_reasoning(self, response: str) -> str:
        for candidate in self._json_candidates(response):
            pos = response.find(candidate)
            if pos >= 0:
                before = response[:pos].strip()
                after = response[pos + len(candidate):].strip()
                parts = [p for p in [before, after] if p]
                return " ".join(parts) if parts else ""
        return response.strip()


async def main():
    agent = AsyncAIAgent()
    print("Welcome to Scout! Type 'exit' to quit.")
    while True:
        try:
            user_input = input("> ")
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Goodbye!")
            break

        if user_input.strip().lower() == "exit":
            break

        try:
            response = await agent.get_ai_response(user_input)
            print(f"\n🤖 {response}\n")
        except Exception as e:
            print(f"❌ Error: {e}")


# Sync helper
def get_ai_response(prompt: str) -> str:
    agent = AsyncAIAgent()
    return asyncio.run(agent.get_ai_response(prompt))


if __name__ == "__main__":
    asyncio.run(main())
