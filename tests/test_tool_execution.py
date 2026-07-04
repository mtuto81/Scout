import pytest
import asyncio
from agent import AsyncAIAgent


class MockToolManager:
    def __init__(self):
        self.calls = 0

    async def execute_tool_call(self, name, args):
        self.calls += 1

        if self.calls < 2:
            return {
                "tool": name,
                "success": False,
                "result": "temporary failure",
                "error": "fail"
            }

        return {
            "tool": name,
            "success": True,
            "result": "ok"
        }