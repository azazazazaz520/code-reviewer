"""Tool Registry — 全局工具注册中心。

通过 @register_tool 装饰器注册 Tool。
Tool 的 Schema 自动从函数签名和 docstring 提取。
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

TOOL_REGISTRY: dict[str, dict[str, Any]] = {}


def register_tool(
    name: str | None = None,
    description: str | None = None,
    toolset: str = "default",
) -> Callable:
    """装饰器：将函数注册为 Tool。

    自动从函数签名提取参数 schema。
    """

    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__

        # 从函数签名提取参数 schema
        sig = inspect.signature(func)
        properties = {}
        required = []
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            param_type = "string"
            if param.annotation is not inspect.Parameter.empty:
                type_map = {int: "integer", float: "number", bool: "boolean", str: "string"}
                param_type = type_map.get(param.annotation, "string")
            properties[param_name] = {"type": param_type, "description": param_name}
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        TOOL_REGISTRY[tool_name] = {
            "name": tool_name,
            "description": description or (func.__doc__ or "").strip().split("\n")[0],
            "toolset": toolset,
            "handler": func,
            "schema": {
                "name": tool_name,
                "description": description or (func.__doc__ or "").strip(),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
        return func

    return decorator


def get_tools_for_reviewer(tool_names: list[str]) -> list[dict]:
    """返回指定名称的 Tool Schema 列表。"""
    return [TOOL_REGISTRY[name]["schema"] for name in tool_names if name in TOOL_REGISTRY]
