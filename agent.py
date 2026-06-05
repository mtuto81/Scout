import asyncio
import platform
from openai import AsyncOpenAI
from config import get_llm_config
from tool_manager import AsyncToolManager
from logger import Logger
import json
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
        self.max_history_messages = 20

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

        recent_history = self.conversation_history[-self.max_history_messages:]
        messages = [{"role": "system", "content": system_prompt}] + recent_history

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
        )

        return response.choices[0].message.content

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        parsed = self._parse_json_payload(response)
        if parsed is None:
            return []

        if isinstance(parsed, dict) and "tool_calls" in parsed:
            parsed = parsed["tool_calls"]

        if isinstance(parsed, dict) and "tool" in parsed:
            parsed.setdefault("args", {})
            return [parsed]

        if isinstance(parsed, list):
            valid_calls = []
            for call in parsed:
                if isinstance(call, dict) and "tool" in call:
                    call.setdefault("args", {})
                    valid_calls.append(call)
            return valid_calls

        return []

    def _parse_json_payload(self, response: str) -> Any:
        text = response.strip()
        try:
            return json.loads(text)
        except Exception:
            pass

        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
            try:
                return json.loads(text)
            except Exception:
                pass

        starts = [pos for pos in (text.find("{"), text.find("[")) if pos != -1]
        if not starts:
            return None
        start = min(starts)
        end = max(text.rfind("}"), text.rfind("]"))
        if end <= start:
            return None
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return None

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
        self._add_message(
            "user",
            "Tool results:\n" + json.dumps(tool_results, ensure_ascii=False, indent=2),
        )

    def _add_message(self, role: str, content: str) -> None:
        self.conversation_history.append({"role": role, "content": content})
        if len(self.conversation_history) > self.max_history_messages:
            self.conversation_history = self.conversation_history[-self.max_history_messages:]

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
