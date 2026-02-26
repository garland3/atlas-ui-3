"""
Lightweight Prefect API client using httpx.
Avoids adding the heavy `prefect` package as a dependency to the Atlas container.
Communicates with the Prefect server REST API directly.
"""

import asyncio
import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

PREFECT_API_URL = os.environ.get("PREFECT_API_URL", "http://prefect-server.atlas:4200/api")

# Flow deployment name and timeout defaults
DEPLOYMENT_NAME = "python-runner/python-runner-k8s"
DEFAULT_TIMEOUT = 120
MAX_TIMEOUT = 600
POLL_INTERVAL = 2

# Terminal states for a Prefect flow run
TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED", "CRASHED", "CANCELLING"}


class PrefectAPIError(Exception):
    """Raised when the Prefect API returns an unexpected response."""


async def get_deployment_id(client: httpx.AsyncClient) -> str:
    """Look up the deployment ID for the python-runner-k8s deployment."""
    resp = await client.post(
        f"{PREFECT_API_URL}/deployments/filter",
        json={
            "deployments": {
                "name": {"any_": ["python-runner-k8s"]},
            },
            "limit": 1,
        },
    )
    resp.raise_for_status()
    deployments = resp.json()
    if not deployments:
        raise PrefectAPIError(
            "Deployment 'python-runner-k8s' not found. "
            "Run deploy/prefect/deploy_flow.py to register the flow."
        )
    return deployments[0]["id"]


async def create_flow_run(client: httpx.AsyncClient, code: str, timeout_seconds: int) -> str:
    """Create a flow run for the python-runner deployment.

    Args:
        client: httpx async client.
        code: Python source code to execute.
        timeout_seconds: Job timeout in seconds.

    Returns:
        The flow run ID.
    """
    deployment_id = await get_deployment_id(client)

    resp = await client.post(
        f"{PREFECT_API_URL}/deployments/{deployment_id}/create_flow_run",
        json={
            "parameters": {"code": code},
            "tags": ["atlas-mcp", "k3s-job-runner"],
        },
    )
    resp.raise_for_status()
    flow_run = resp.json()
    flow_run_id = flow_run["id"]
    logger.info("Created flow run %s for deployment %s", flow_run_id, deployment_id)
    return flow_run_id


async def wait_for_completion(client: httpx.AsyncClient, flow_run_id: str, timeout_seconds: int) -> dict:
    """Poll the Prefect API until the flow run reaches a terminal state.

    Args:
        client: httpx async client.
        flow_run_id: The flow run to monitor.
        timeout_seconds: Maximum wait time.

    Returns:
        The flow run object from the API.

    Raises:
        PrefectAPIError: If the run does not complete within the timeout.
    """
    start = time.monotonic()
    while True:
        elapsed = time.monotonic() - start
        if elapsed > timeout_seconds:
            raise PrefectAPIError(
                f"Flow run {flow_run_id} did not complete within {timeout_seconds}s"
            )

        resp = await client.get(f"{PREFECT_API_URL}/flow_runs/{flow_run_id}")
        resp.raise_for_status()
        flow_run = resp.json()

        state_type = flow_run.get("state", {}).get("type", "UNKNOWN").upper()
        state_name = flow_run.get("state", {}).get("name", "Unknown")
        logger.debug("Flow run %s state: %s (%s)", flow_run_id, state_name, state_type)

        if state_type in TERMINAL_STATES:
            return flow_run

        await asyncio.sleep(POLL_INTERVAL)


async def get_flow_run_result(client: httpx.AsyncClient, flow_run: dict) -> dict:
    """Extract the result from a completed flow run.

    The python-runner flow returns a dict with stdout, stderr, success, error.
    If the state has a result artifact, we fetch it; otherwise we return
    state information.

    Args:
        client: httpx async client.
        flow_run: The flow run object.

    Returns:
        Dict with stdout, stderr, success, error, and state info.
    """
    state = flow_run.get("state", {})
    state_type = state.get("type", "UNKNOWN").upper()
    state_name = state.get("name", "Unknown")
    state_message = state.get("message", "")

    result = {
        "flow_run_id": flow_run["id"],
        "state": state_name,
        "state_type": state_type,
        "state_message": state_message,
        "stdout": "",
        "stderr": "",
        "success": state_type == "COMPLETED",
        "error": None,
    }

    # Try to get the result artifact from the state
    if state_type == "COMPLETED" and state.get("state_details", {}).get("result_artifact_id"):
        artifact_id = state["state_details"]["result_artifact_id"]
        try:
            resp = await client.get(f"{PREFECT_API_URL}/artifacts/{artifact_id}")
            resp.raise_for_status()
            artifact = resp.json()
            data = artifact.get("data")
            if isinstance(data, dict):
                result["stdout"] = data.get("stdout", "")
                result["stderr"] = data.get("stderr", "")
                result["success"] = data.get("success", False)
                result["error"] = data.get("error")
        except Exception as e:
            logger.warning("Could not fetch result artifact %s: %s", artifact_id, e)

    if state_type in ("FAILED", "CRASHED"):
        result["error"] = state_message or f"Flow run {state_name}"

    return result


async def get_flow_run_logs(client: httpx.AsyncClient, flow_run_id: str) -> str:
    """Retrieve logs for a flow run from the Prefect API.

    Args:
        client: httpx async client.
        flow_run_id: The flow run whose logs to fetch.

    Returns:
        Concatenated log messages as a string.
    """
    resp = await client.post(
        f"{PREFECT_API_URL}/logs/filter",
        json={
            "logs": {
                "flow_run_id": {"any_": [flow_run_id]},
            },
            "sort": "TIMESTAMP_ASC",
            "limit": 200,
        },
    )
    resp.raise_for_status()
    logs = resp.json()

    lines = []
    for entry in logs:
        timestamp = entry.get("timestamp", "")
        level = entry.get("level", 0)
        message = entry.get("message", "")
        level_name = {10: "DEBUG", 20: "INFO", 30: "WARNING", 40: "ERROR", 50: "CRITICAL"}.get(
            level, str(level)
        )
        lines.append(f"[{timestamp}] {level_name}: {message}")

    return "\n".join(lines)


async def run_python_job(code: str, timeout_seconds: int = DEFAULT_TIMEOUT) -> dict:
    """Submit Python code to the Prefect flow runner and wait for results.

    This is the main entry point used by the MCP tool.

    Args:
        code: Python source code to execute.
        timeout_seconds: Maximum execution time (capped at MAX_TIMEOUT).

    Returns:
        Dict with stdout, stderr, success, error, logs, flow_run_id.
    """
    timeout_seconds = min(max(timeout_seconds, 10), MAX_TIMEOUT)

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        # Verify server is reachable
        try:
            health = await client.get(f"{PREFECT_API_URL}/health")
            health.raise_for_status()
        except Exception as e:
            return {
                "success": False,
                "error": f"Prefect server is not reachable at {PREFECT_API_URL}: {e}",
                "stdout": "",
                "stderr": "",
                "logs": "",
                "flow_run_id": None,
            }

        flow_run_id = await create_flow_run(client, code, timeout_seconds)
        flow_run = await wait_for_completion(client, flow_run_id, timeout_seconds)
        result = await get_flow_run_result(client, flow_run)

        # Fetch logs for additional context
        try:
            logs = await get_flow_run_logs(client, flow_run_id)
            result["logs"] = logs
        except Exception as e:
            logger.warning("Could not fetch logs for flow run %s: %s", flow_run_id, e)
            result["logs"] = f"(log retrieval failed: {e})"

        return result
