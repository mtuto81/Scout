import asyncio
import inspect
import importlib.util
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Callable, Dict, List, Mapping


JsonSchema = Dict[str, Any]


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: JsonSchema
    handler: Callable[..., Any]
    risk: str = "low"
    aliases: List[str] = field(default_factory=list)

    def prompt_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "risk": self.risk,
            "parameters": self.parameters,
        }


class AsyncToolManager:
    """Explicit async/sync tool registry with lightweight argument validation.

    Tool modules should expose a TOOLS list. Each item is a dict with:
    name, description, parameters, handler, risk, and optional aliases.
    """

    def __init__(self, tools_directory: str = "tools"):
        self.tools_directory = tools_directory
        self.tools: Dict[str, ToolSpec] = {}
        self.aliases: Dict[str, str] = {}
        self.load_errors: List[str] = []
        self._loaded = False
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ScoutTool")

    def _tools_path(self) -> str:
        if os.path.isabs(self.tools_directory):
            return self.tools_directory

        candidates = [
            os.path.join(os.getcwd(), self.tools_directory),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), self.tools_directory),
        ]

        bundle_dir = getattr(sys, "_MEIPASS", None)
        if bundle_dir:
            candidates.insert(0, os.path.join(bundle_dir, self.tools_directory))

        executable_dir = os.path.dirname(sys.executable)
        if executable_dir:
            candidates.append(os.path.join(executable_dir, self.tools_directory))

        for candidate in candidates:
            if os.path.isdir(candidate):
                return os.path.abspath(candidate)

        return os.path.abspath(self.tools_directory)

    def _discover_tools(self) -> None:
        if self._loaded:
            return

        tools_path = self._tools_path()
        if not os.path.isdir(tools_path):
            self.load_errors.append(f"Tool directory not found: {tools_path}")
            self._loaded = True
            return

        for filename in sorted(os.listdir(tools_path)):
            if not filename.endswith(".py") or filename.startswith("__"):
                continue

            module_name = filename[:-3]
            module_path = os.path.join(tools_path, filename)
            module_key = f"tools.{module_name}"

            try:
                if module_key in sys.modules:
                    module = sys.modules[module_key]
                else:
                    spec = importlib.util.spec_from_file_location(module_key, module_path)
                    if not spec or not spec.loader:
                        continue
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_key] = module
                    spec.loader.exec_module(module)
            except Exception as exc:
                self._record_load_error(f"Skipped {filename}: {exc}")
                continue

            for tool_def in getattr(module, "TOOLS", []):
                try:
                    self.register(tool_def)
                except Exception as exc:
                    name = tool_def.get("name", "unknown") if isinstance(tool_def, dict) else "unknown"
                    self._record_load_error(f"Skipped tool '{name}' in {filename}: {exc}")

        self._loaded = True

    def _record_load_error(self, message: str) -> None:
        self.load_errors.append(message)

    def get_load_errors(self) -> List[str]:
        self._discover_tools()
        return list(self.load_errors)

    def register(self, tool_def: Mapping[str, Any]) -> None:
        name = str(tool_def["name"]).strip()
        handler = tool_def["handler"]
        if not name:
            raise ValueError("Tool name cannot be empty.")
        if name in self.tools:
            raise ValueError(f"Duplicate tool name: {name}")
        if not callable(handler):
            raise TypeError(f"Tool '{name}' handler is not callable.")

        parameters = dict(tool_def.get("parameters") or {"type": "object", "properties": {}})
        parameters.setdefault("type", "object")
        parameters.setdefault("properties", {})

        spec = ToolSpec(
            name=name,
            description=str(tool_def.get("description", "")).strip(),
            parameters=parameters,
            handler=handler,
            risk=str(tool_def.get("risk", "low")).strip().lower() or "low",
            aliases=list(tool_def.get("aliases", [])),
        )
        self.tools[name] = spec
        for alias in spec.aliases:
            self.aliases[str(alias)] = name

    def get_tool_names(self) -> List[str]:
        self._discover_tools()
        return sorted(self.tools.keys())

    def describe_tools(self) -> List[Dict[str, Any]]:
        self._discover_tools()
        return [self.tools[name].prompt_dict() for name in self.get_tool_names()]

    def resolve_tool_name(self, tool_name: str) -> str:
        self._discover_tools()
        if tool_name in self.tools:
            return tool_name
        return self.aliases.get(tool_name, tool_name)

    def is_async_tool(self, tool_name: str) -> bool:
        self._discover_tools()
        spec = self.tools.get(self.resolve_tool_name(tool_name))
        return bool(spec and inspect.iscoroutinefunction(spec.handler))

    async def execute_tool_call(self, tool_name: str, args: Any = None) -> Dict[str, Any]:
        self._discover_tools()
        resolved_name = self.resolve_tool_name(tool_name)
        spec = self.tools.get(resolved_name)
        if not spec:
            raise ValueError(f"Tool '{tool_name}' not found. Available tools: {', '.join(self.get_tool_names())}")

        kwargs = self._coerce_args(spec, args)
        try:
            if inspect.iscoroutinefunction(spec.handler):
                result = await spec.handler(**kwargs)
            else:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    self._executor,
                    partial(spec.handler, **kwargs),
                )

            return {
                "tool": spec.name,
                "args": kwargs,
                "risk": spec.risk,
                "success": True,
                "result": self._normalize_result(result),
            }
        except Exception as exc:
            return {
                "tool": spec.name,
                "args": kwargs,
                "risk": spec.risk,
                "success": False,
                "result": str(exc),
                "error": str(exc),
            }

    async def execute_tool_async(self, tool_name: str, *args: Any, **kwargs: Any) -> Any:
        tool_args = kwargs if kwargs else list(args)
        result = await self.execute_tool_call(tool_name, tool_args)
        if not result["success"]:
            raise RuntimeError(result["result"])
        return result["result"]

    def execute_tool(self, tool_name: str, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Use execute_tool_call from async code.")

    def _coerce_args(self, spec: ToolSpec, args: Any) -> Dict[str, Any]:
        schema = spec.parameters or {}
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))

        if args is None:
            incoming: Dict[str, Any] = {}
        elif isinstance(args, Mapping):
            incoming = dict(args)
        elif isinstance(args, list):
            keys = list(properties.keys())
            incoming = {key: value for key, value in zip(keys, args)}
        else:
            raise TypeError(f"Arguments for tool '{spec.name}' must be an object or list.")

        unknown = sorted(set(incoming) - set(properties))
        if unknown:
            raise ValueError(f"Unknown argument(s) for '{spec.name}': {', '.join(unknown)}")

        coerced: Dict[str, Any] = {}
        for name, prop in properties.items():
            if name in incoming:
                coerced[name] = self._coerce_value(name, incoming[name], prop)
            elif "default" in prop:
                coerced[name] = prop["default"]
            elif name in required:
                raise ValueError(f"Missing required argument '{name}' for tool '{spec.name}'")

        return coerced

    def _coerce_value(self, name: str, value: Any, prop: Mapping[str, Any]) -> Any:
        expected = prop.get("type")
        if expected == "string":
            if not isinstance(value, str):
                raise TypeError(f"Argument '{name}' must be a string.")
            return value
        if expected == "integer":
            if isinstance(value, bool):
                raise TypeError(f"Argument '{name}' must be an integer.")
            return int(value)
        if expected == "number":
            if isinstance(value, bool):
                raise TypeError(f"Argument '{name}' must be a number.")
            return float(value)
        if expected == "boolean":
            if not isinstance(value, bool):
                raise TypeError(f"Argument '{name}' must be a boolean.")
            return value
        if expected == "array" and not isinstance(value, list):
            raise TypeError(f"Argument '{name}' must be an array.")
        if expected == "object" and not isinstance(value, dict):
            raise TypeError(f"Argument '{name}' must be an object.")
        return value

    def _normalize_result(self, result: Any) -> str:
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result, ensure_ascii=False, indent=2)
        except TypeError:
            return str(result)
