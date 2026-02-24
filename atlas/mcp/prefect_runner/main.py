#!/usr/bin/env python3
"""
Prefect Runner MCP Server using FastMCP.

Takes a flow definition (produced by the Prefect Planner MCP) and submits
it to a Prefect work pool as a deployment/job.  Communicates with either
a real Prefect server or the mock server in mocks/prefect-orchestration-mock.

Tools:
    create_work_pool   - Create or ensure a Prefect work pool exists.
    submit_flow        - Deploy a flow and start a run on a work pool.
    get_run_status     - Check the status of a running flow.
    list_work_pools    - Show available work pools.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import requests
from fastmcp import Context, FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("Prefect Runner")

PREFECT_API_URL = os.environ.get("PREFECT_API_URL", "http://127.0.0.1:4220")


def _api(method: str, path: str, payload: Optional[Dict] = None) -> Dict[str, Any]:
    """Call the Prefect API (real or mock) and return the JSON response."""
    url = f"{PREFECT_API_URL}{path}"
    try:
        resp = requests.request(method, url, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as exc:
        body = ""
        if exc.response is not None:
            body = exc.response.text[:500]
        return {"error": f"HTTP {exc.response.status_code if exc.response else '?'}: {body}"}
    except requests.ConnectionError:
        return {"error": f"Cannot connect to Prefect API at {PREFECT_API_URL}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool
async def create_work_pool(
    pool_name: str,
    pool_type: str = "process",
    description: str = "",
    concurrency_limit: Optional[int] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Create a Prefect work pool (or return existing one).

    A work pool is where deployments are submitted and workers pick up
    jobs.  This tool ensures the pool exists before you submit flows.

    Args:
        pool_name: Name for the work pool (e.g. "ml-gpu-pool").
        pool_type: Worker type - "process", "docker", "kubernetes", etc.
        description: Human-readable description of the pool.
        concurrency_limit: Max concurrent flow runs (None = unlimited).

    Returns:
        The work pool object from the Prefect API.
    """
    if ctx:
        await ctx.report_progress(
            progress=0, total=2,
            message=f"Creating work pool '{pool_name}'...",
        )

    # Check if already exists
    existing = _api("GET", f"/api/work_pools/{pool_name}")
    if "error" not in existing:
        if ctx:
            await ctx.report_progress(
                progress=2, total=2,
                message=f"Work pool '{pool_name}' already exists.",
            )
        return {
            "results": {
                "success": True,
                "action": "existing",
                "work_pool": existing,
                "message": f"Work pool '{pool_name}' already exists.",
            }
        }

    result = _api("POST", "/api/work_pools/", {
        "name": pool_name,
        "type": pool_type,
        "description": description,
        "concurrency_limit": concurrency_limit,
    })

    if "error" in result:
        return {"results": {"success": False, **result}}

    if ctx:
        await ctx.report_progress(
            progress=2, total=2,
            message=f"Work pool '{pool_name}' created.",
        )

    return {
        "results": {
            "success": True,
            "action": "created",
            "work_pool": result,
            "message": f"Work pool '{pool_name}' created with type '{pool_type}'.",
        }
    }


@mcp.tool
async def submit_flow(
    flow_definition: str,
    work_pool_name: str,
    deployment_name: str = "",
    parameters: Optional[str] = None,
    tags: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Deploy a Prefect flow to a work pool and start a flow run.

    Takes the flow_definition JSON (from the Prefect Planner's
    plan_prefect_flow tool) and submits it as a deployment assigned
    to the given work pool.  A flow run is created immediately.

    Args:
        flow_definition: JSON string of the flow definition from the planner.
            Must contain "flow_name" and "tasks" keys.
        work_pool_name: Name of the work pool to assign the job to.
        deployment_name: Optional deployment name (defaults to flow_name).
        parameters: Optional JSON string of runtime parameters.
        tags: Optional comma-separated tags (e.g. "ml,production").

    Returns:
        Deployment and flow run details including the run_id for polling.
    """
    # Parse inputs
    try:
        flow_def = json.loads(flow_definition)
    except (json.JSONDecodeError, TypeError):
        return {
            "results": {
                "success": False,
                "error": "flow_definition must be a valid JSON string.",
            }
        }

    flow_name = flow_def.get("flow_name", "unnamed_flow")
    dep_name = deployment_name or f"{flow_name}_deployment"

    runtime_params: Dict[str, Any] = {}
    if parameters:
        try:
            runtime_params = json.loads(parameters)
        except (json.JSONDecodeError, TypeError):
            pass

    tag_list: List[str] = []
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    if ctx:
        await ctx.report_progress(
            progress=0, total=3,
            message=f"Creating deployment '{dep_name}' on pool '{work_pool_name}'...",
        )

    # Step 1: Create deployment
    dep_result = _api("POST", "/api/deployments/", {
        "name": dep_name,
        "flow_name": flow_name,
        "work_pool_name": work_pool_name,
        "parameters": runtime_params,
        "tags": tag_list,
        "description": flow_def.get("description", ""),
        "flow_definition": flow_def,
    })

    if "error" in dep_result:
        return {"results": {"success": False, "stage": "deployment", **dep_result}}

    dep_id = dep_result.get("id", "")
    if ctx:
        await ctx.report_progress(
            progress=1, total=3,
            message=f"Deployment '{dep_id}' created.  Starting flow run...",
        )

    # Step 2: Create flow run from deployment
    run_result = _api("POST", f"/api/deployments/{dep_id}/create_flow_run", {
        "parameters": runtime_params,
        "tags": tag_list,
    })

    if "error" in run_result:
        return {"results": {"success": False, "stage": "flow_run", **run_result}}

    run_id = run_result.get("id", "")
    if ctx:
        await ctx.report_progress(
            progress=3, total=3,
            message=f"Flow run '{run_id}' submitted to work pool '{work_pool_name}'.",
        )

    return {
        "results": {
            "success": True,
            "deployment_id": dep_id,
            "deployment_name": dep_name,
            "flow_run_id": run_id,
            "flow_name": flow_name,
            "work_pool_name": work_pool_name,
            "state": run_result.get("state", {}),
            "message": (
                f"Flow '{flow_name}' deployed and run '{run_id}' submitted "
                f"to work pool '{work_pool_name}'."
            ),
        }
    }


@mcp.tool
async def get_run_status(
    flow_run_id: str,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Check the status of a Prefect flow run.

    Polls the Prefect API for the current state of the given flow run,
    including task run details if available.

    Args:
        flow_run_id: The flow run ID returned by submit_flow.

    Returns:
        Current state, timing info, and task run details.
    """
    if ctx:
        await ctx.report_progress(
            progress=0, total=1,
            message=f"Checking run {flow_run_id}...",
        )

    result = _api("GET", f"/api/flow_runs/{flow_run_id}")
    if "error" in result:
        return {"results": {"success": False, **result}}

    if ctx:
        state_type = result.get("state", {}).get("type", "UNKNOWN")
        await ctx.report_progress(
            progress=1, total=1,
            message=f"Run state: {state_type}",
        )

    return {
        "results": {
            "success": True,
            "flow_run_id": flow_run_id,
            "flow_name": result.get("flow_name", ""),
            "state": result.get("state", {}),
            "start_time": result.get("start_time"),
            "end_time": result.get("end_time"),
            "task_run_ids": result.get("task_runs", []),
            "parameters": result.get("parameters", {}),
        }
    }


@mcp.tool
def list_work_pools() -> Dict[str, Any]:
    """List all available Prefect work pools.

    Returns:
        A list of work pool objects with status and pending work counts.
    """
    result = _api("GET", "/api/work_pools/")
    if isinstance(result, dict) and "error" in result:
        return {"results": {"success": False, **result}}

    pools = result if isinstance(result, list) else []
    return {
        "results": {
            "success": True,
            "total_pools": len(pools),
            "work_pools": [
                {
                    "name": p.get("name", ""),
                    "type": p.get("type", ""),
                    "status": p.get("status", ""),
                    "pending_work": p.get("pending_work", 0),
                    "concurrency_limit": p.get("concurrency_limit"),
                }
                for p in pools
            ],
        }
    }


if __name__ == "__main__":
    mcp.run(show_banner=False)
