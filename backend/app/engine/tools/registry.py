"""Tool Registry — 全局工具注册中心。

通过 @register_tool 装饰器注册 Tool。
Tool 的 Schema 自动从函数签名和 docstring 提取。
"""

from __future__ import annotations

import inspect
import re
from typing import Any, Callable, get_type_hints

TOOL_REGISTRY: dict[str, dict[str, Any]] = {}

READ_FILE_MAX_LINES = 200

# 这些约束同时用于给模型展示的 JSON Schema 和执行前的参数校验，避免
# Schema 允许的值与实际 Tool 边界不一致。
TOOL_PARAMETER_CONSTRAINTS: dict[str, dict[str, dict[str, int]]] = {
    "ReadFile": {
        "start_line": {"minimum": 1},
        "max_lines": {"minimum": 1, "maximum": READ_FILE_MAX_LINES},
    },
    "GetReviewContext": {"max_depth": {"minimum": 1}},
    "GetImpactRadius": {"max_depth": {"minimum": 1}},
    "GetHubNodes": {"top_n": {"minimum": 1}},
    "GetBridgeNodes": {"top_n": {"minimum": 1}},
    "GetPRDiff": {"pr_number": {"minimum": 1}},
    "GetPRChangedFiles": {"pr_number": {"minimum": 1}},
}


class ToolArgumentError(ValueError):
    """Tool 参数未满足类型或范围约束时抛出的可读错误。"""


def _schema_type(annotation: object) -> str:
    """把已解析的 Python 注解映射为 JSON Schema 基础类型。"""
    type_map = {int: "integer", float: "number", bool: "boolean", str: "string"}
    return type_map.get(annotation, "string")


def _resolved_annotations(func: Callable) -> dict[str, object]:
    """解析 postponed annotations；第三方或动态函数失败时保留签名回退。"""
    try:
        return get_type_hints(func)
    except (NameError, TypeError):
        return {}


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

        # 从函数签名提取参数 schema。项目启用了 postponed annotations，
        # 直接读取 param.annotation 会得到 "int" 这样的字符串。
        sig = inspect.signature(func)
        annotations = _resolved_annotations(func)
        properties = {}
        required = []
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            param_type = "string"
            annotation = annotations.get(param_name, param.annotation)
            if annotation is not inspect.Parameter.empty:
                param_type = _schema_type(annotation)
            property_schema = {"type": param_type, "description": param_name}
            property_schema.update(
                TOOL_PARAMETER_CONSTRAINTS.get(tool_name, {}).get(param_name, {})
            )
            properties[param_name] = property_schema
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


def coerce_tool_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """在调用边界校验并转换模型参数，拒绝模糊的数值截断。"""
    entry = TOOL_REGISTRY.get(tool_name)
    if not entry:
        raise ToolArgumentError(f"未知 Tool：{tool_name}")

    properties = entry["schema"]["parameters"].get("properties", {})
    normalised = dict(arguments)
    signature = inspect.signature(entry["handler"])
    for name, parameter in signature.parameters.items():
        if name not in normalised and parameter.default is not inspect.Parameter.empty:
            normalised[name] = parameter.default
    for name, value in normalised.items():
        schema = properties.get(name)
        if schema is None:
            raise ToolArgumentError(f"{tool_name} 不支持参数：{name}")
        expected = schema.get("type")
        if expected == "integer":
            if isinstance(value, bool):
                raise ToolArgumentError(f"{tool_name}.{name} 必须是整数")
            if isinstance(value, str):
                text = value.strip()
                if not re.fullmatch(r"[+-]?\d+", text):
                    raise ToolArgumentError(f"{tool_name}.{name} 必须是整数")
                value = int(text)
            elif not isinstance(value, int):
                raise ToolArgumentError(f"{tool_name}.{name} 必须是整数")
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            if minimum is not None and value < minimum:
                raise ToolArgumentError(f"{tool_name}.{name} 必须大于等于 {minimum}")
            if maximum is not None and value > maximum:
                raise ToolArgumentError(f"{tool_name}.{name} 必须小于等于 {maximum}")
        elif expected == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ToolArgumentError(f"{tool_name}.{name} 必须是数字")
        elif expected == "boolean" and not isinstance(value, bool):
            raise ToolArgumentError(f"{tool_name}.{name} 必须是布尔值")
        elif expected == "string" and not isinstance(value, str):
            raise ToolArgumentError(f"{tool_name}.{name} 必须是字符串")
        normalised[name] = value

    for name in entry["schema"]["parameters"].get("required", []):
        if name not in normalised:
            raise ToolArgumentError(f"{tool_name} 缺少必填参数：{name}")
    return normalised


def get_tools_for_reviewer(tool_names: list[str]) -> list[dict]:
    """返回指定名称的 Tool Schema 列表。"""
    return [TOOL_REGISTRY[name]["schema"] for name in tool_names if name in TOOL_REGISTRY]
