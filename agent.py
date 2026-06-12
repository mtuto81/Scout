import asyncio
import platform
from openai import AsyncOpenAI
from config import get_llm_config
from tool_manager import AsyncToolManager
from logger import Logger
import json
import re
from typing import Callable, Dict, List, Any, Optional


class AsyncAIAgent:
    def __init__(self, event_callback: Optional[Callable[[str], None]] = None):
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
        self.conversation_history: List[Dict[str, Any]] = []
        self.max_iterations = 10

    async def get_ai_response(self, prompt: str) -> str:
        self._add_message("user", prompt)
        try:
            self.logger.log({"user_prompt": prompt})
        except Exception:
            pass

        for iteration in range(self.max_iterations):
            self._emit_event(f"Agent thinking... iteration {iteration + 1}")
            ai_response = await self._get_ai_decision()
            tool_calls = self._parse_tool_calls(ai_response)
            if not tool_calls:
                self._add_message("assistant", ai_response)
                try:
                    self.logger.log({"final_response": ai_response})
                except Exception:
                    pass
                return ai_response

            self._emit_event(f"Executing {len(tool_calls)} tool(s)...")
            tool_results = await self._execute_tools_and_wait(tool_calls)
            self._add_tool_results_to_history(tool_calls, tool_results)

        fallback_response = "I've reached my thinking limit. Let me provide what I have so far."
        self._add_message("assistant", fallback_response)
        return fallback_response

    async def _get_ai_decision(self) -> str:
        tool_schemas = json.dumps(self.tool_manager.describe_tools(), ensure_ascii=False, indent=2)

        system_prompt = f"""
You are Scout, a highly capable IT AI assistant with access to tools. You solve user requests by reasoning step-by-step and calling tools when needed.
The assistant is running on a {platform.system()} machine.

## Your Capabilities:
- Think carefully before acting.
- You may call one or more tools per step.
- Prefer safe read-only inspection tools before tools that change files or system state.
- Ask the user before high-risk actions unless the tool itself asks for confirmation.
- Always return results to the user, integrating tool outputs into a final answer.

## Available Tools
{tool_schemas}

## Response Rules:
1. If you can answer directly, do so without calling tools.
2. If you need tools, respond ONLY with this JSON object and no markdown:
{{"tool_calls":[{{"tool":"tool_name","args":{{"arg_name":"value"}}}}]}}
3. Use object-style args that match the tool schema. Use {{}} for tools with no arguments.
4. After receiving tool results, summarize them and conclude.
5. Do not claim a tool succeeded unless the tool result says success is true.


"""

        messages = [{"role": "system", "content": system_prompt}] + list(self.conversation_history)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
        )

        return response.choices[0].message.content

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        parse_errors = []
        saw_tool_payload = False

        for candidate in self._json_candidates(response.strip()):
            parsed = self._loads_json_candidate(candidate)
            if parsed is None:
                continue

            tool_calls, errors, saw_payload = self._tool_calls_from_parsed(parsed)
            saw_tool_payload = saw_tool_payload or saw_payload
            if tool_calls:
                return tool_calls
            parse_errors.extend(errors)

        if self._looks_like_tool_payload(response):
            saw_tool_payload = True

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
        try:
            try:
                self.logger.log({"tool_call": {"name": tool_name, "args": args}})
            except Exception:
                pass

            result = await self.tool_manager.execute_tool_call(tool_name, args)

            try:
                self.logger.log({"tool_result": {"tool": tool_name, "result": result}})
            except Exception:
                pass

            return result

        except Exception as e:
            err = str(e)
            try:
                self.logger.log({"tool_error": {"tool": tool_name, "error": err}})
            except Exception:
                pass
            return {"tool": tool_name, "args": args, "success": False, "result": err, "error": err}

    def _add_tool_results_to_history(self, tool_calls: List[Dict[str, Any]], tool_results: List[Dict[str, Any]]):
        self._add_message("assistant", json.dumps({"tool_calls": tool_calls}, ensure_ascii=False))
        failed_tools = [result for result in tool_results if not result.get("success", False)]
        recovery_instruction = ""
        if failed_tools:
            recovery_instruction = (
                "\n\nRecovery instruction:\n"
                "One or more tools failed. Do not finalize with only the failure unless the task is impossible or unsafe. "
                "Try a safer corrected tool call, use a different read-only diagnostic command, or ask the user for the missing information."
            )
        self._add_message(
            "user",
            "Tool results:\n" + json.dumps(tool_results, ensure_ascii=False, indent=2) + recovery_instruction,
        )

    def _add_message(self, role: str, content: str) -> None:
        self.conversation_history.append({"role": role, "content": content})

    def _emit_event(self, message: str) -> None:
        if self.event_callback:
            self.event_callback(message)
        else:
            print(message)


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
