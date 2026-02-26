"""
K3s Job Runner MCP Server.

Submits Python code to a Prefect-orchestrated K8s Job and returns results.
Uses httpx to communicate with the Prefect REST API (no heavy prefect
dependency required in the Atlas container).
"""

import logging
import time
from typing import Any, Dict

from fastmcp import FastMCP
from prefect_client import run_python_job

logger = logging.getLogger(__name__)

mcp = FastMCP("K3s Job Runner")

MAX_CODE_LENGTH = 50_000
DEFAULT_TIMEOUT = 120
MAX_TIMEOUT = 600


@mcp.tool
async def run_python_job_tool(
    code: str,
    timeout_seconds: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """Execute Python code as a Kubernetes Job orchestrated by Prefect.

    The code runs in an isolated python:3.12-slim container in the K8s cluster.
    Standard library and common packages are available. The container has no
    network access to the K8s API and runs as a non-root user with a read-only
    root filesystem.

    Good for:
    - Data processing and analysis scripts
    - Mathematical computations
    - Text processing
    - Algorithm prototyping
    - Any CPU-bound Python task

    Limitations:
    - No persistent filesystem (container is ephemeral)
    - No network access from the job container
    - 256Mi memory limit, 500m CPU limit
    - Output is truncated at 100,000 characters
    - Code length limit: 50,000 characters

    Args:
        code: Python source code to execute. Must be valid Python 3.12.
        timeout_seconds: Maximum execution time in seconds (10-600, default 120).

    Returns:
        Dict with execution results:
        {
            "results": {
                "stdout": str,
                "stderr": str,
                "success": bool,
                "error": str | None,
                "flow_run_id": str,
                "logs": str
            },
            "meta_data": {
                "is_error": bool,
                "elapsed_ms": float,
                "timeout_seconds": int,
                "code_length": int
            }
        }
    """
    start = time.perf_counter()
    meta: Dict[str, Any] = {
        "code_length": len(code),
        "timeout_seconds": min(max(timeout_seconds, 10), MAX_TIMEOUT),
    }

    # Validate code length
    if len(code) > MAX_CODE_LENGTH:
        meta["is_error"] = True
        meta["reason"] = "code_too_long"
        meta["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
        return {
            "results": {
                "error": f"Code exceeds maximum length of {MAX_CODE_LENGTH} characters ({len(code)} provided)",
                "success": False,
                "stdout": "",
                "stderr": "",
            },
            "meta_data": meta,
        }

    # Validate code is not empty
    if not code.strip():
        meta["is_error"] = True
        meta["reason"] = "empty_code"
        meta["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
        return {
            "results": {
                "error": "Code is empty",
                "success": False,
                "stdout": "",
                "stderr": "",
            },
            "meta_data": meta,
        }

    try:
        result = await run_python_job(
            code=code,
            timeout_seconds=meta["timeout_seconds"],
        )

        meta["is_error"] = not result.get("success", False)
        meta["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
        meta["flow_run_id"] = result.get("flow_run_id")

        return {
            "results": {
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "success": result.get("success", False),
                "error": result.get("error"),
                "flow_run_id": result.get("flow_run_id"),
                "logs": result.get("logs", ""),
            },
            "meta_data": meta,
        }
    except Exception as e:
        logger.exception("Failed to run Python job via Prefect")
        meta["is_error"] = True
        meta["reason"] = type(e).__name__
        meta["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
        return {
            "results": {
                "error": f"Job submission failed: {e}",
                "success": False,
                "stdout": "",
                "stderr": "",
            },
            "meta_data": meta,
        }


if __name__ == "__main__":
    mcp.run(show_banner=False)
