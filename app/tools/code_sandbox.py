"""
CodeSandboxTool — executes Python code in a subprocess.

Blocked imports: os, sys, subprocess, shutil, pathlib.
"""

from __future__ import annotations

import re
import subprocess
import time

from app.schemas.tools import ToolResult
from app.tools.base import BaseTool

_BLOCKED_IMPORTS = {"os", "sys", "subprocess", "shutil", "pathlib"}

# Matches: import os  /  from os import ...  /  import os, sys  /  from pathlib import Path
_IMPORT_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:import|from)\s+(" + "|".join(_BLOCKED_IMPORTS) + r")(?:\s|,|\.)",
)


class CodeSandboxTool(BaseTool):
    """Run Python code in a subprocess sandbox with blocked-import checks."""

    name: str = "code_sandbox"
    timeout_seconds: float = 10.0

    async def _execute(self, input: dict) -> ToolResult:
        code: str = input.get("code", "").strip()
        if not code:
            return self.on_empty()

        # Check for blocked imports
        blocked = _IMPORT_PATTERN.findall(code)
        if blocked:
            return ToolResult(
                tool_name=self.name,
                status="error",
                data={"reason": f"blocked import: {blocked[0]}"},
            )

        start = time.perf_counter()
        try:
            result = subprocess.run(
                ["python3", "-c", code],
                timeout=10,
                capture_output=True,
                text=True,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            return ToolResult(
                tool_name=self.name,
                status="success",
                data={
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.returncode,
                    "latency_ms": round(elapsed_ms, 2),
                },
            )
        except subprocess.TimeoutExpired:
            return self.on_timeout()
        except Exception as exc:
            return self.on_malformed(str(exc))
