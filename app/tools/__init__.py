"""tools package — registry of available tools."""

from app.tools.web_search import WebSearchTool
from app.tools.code_sandbox import CodeSandboxTool
from app.tools.sql_lookup import SQLLookupTool
from app.tools.self_reflection import SelfReflectionTool

TOOL_REGISTRY: dict[str, type] = {
    "web_search": WebSearchTool,
    "code_sandbox": CodeSandboxTool,
    "sql_lookup": SQLLookupTool,
    "self_reflection": SelfReflectionTool,
}

__all__ = [
    "TOOL_REGISTRY",
    "WebSearchTool",
    "CodeSandboxTool",
    "SQLLookupTool",
    "SelfReflectionTool",
]
