"""
Mock Prefect API Server for testing Prefect orchestration MCP tools.

Simulates Prefect's REST API for work pools, deployments, and flow runs
without requiring an actual Prefect server. Stores all state in memory.

Endpoints:
    POST /api/work_pools/              - Create a work pool
    GET  /api/work_pools/{name}        - Get work pool details
    GET  /api/work_pools/              - List all work pools
    POST /api/deployments/             - Create a deployment
    GET  /api/deployments/{id}         - Get deployment details
    POST /api/deployments/{id}/create_flow_run - Start a flow run
    GET  /api/flow_runs/{id}           - Get flow run status
    POST /api/flow_runs/{id}/set_state - Update flow run state
    GET  /api/flow_runs/               - List all flow runs
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(title="Mock Prefect Server", version="0.1.0")

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------
work_pools: Dict[str, Dict[str, Any]] = {}
deployments: Dict[str, Dict[str, Any]] = {}
flow_runs: Dict[str, Dict[str, Any]] = {}
task_runs: Dict[str, Dict[str, Any]] = {}


class FlowRunState(str, Enum):
    SCHEDULED = "SCHEDULED"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class WorkPoolCreate(BaseModel):
    name: str
    type: str = "process"
    description: str = ""
    concurrency_limit: Optional[int] = None
    base_job_template: Optional[Dict[str, Any]] = None


class DeploymentCreate(BaseModel):
    name: str
    flow_name: str
    work_pool_name: str
    parameters: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    description: str = ""
    schedule: Optional[Dict[str, Any]] = None
    # The flow definition: list of task mappings
    flow_definition: Optional[Dict[str, Any]] = None


class FlowRunCreate(BaseModel):
    parameters: Optional[Dict[str, Any]] = None
    state: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class StateUpdate(BaseModel):
    type: str  # SCHEDULED, PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Work pool endpoints
# ---------------------------------------------------------------------------
@app.post("/api/work_pools/")
async def create_work_pool(body: WorkPoolCreate) -> Dict[str, Any]:
    if body.name in work_pools:
        raise HTTPException(409, f"Work pool '{body.name}' already exists")
    pool_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    pool = {
        "id": pool_id,
        "name": body.name,
        "type": body.type,
        "description": body.description,
        "concurrency_limit": body.concurrency_limit,
        "base_job_template": body.base_job_template or {},
        "status": "READY",
        "created": now,
        "updated": now,
        "pending_work": 0,
    }
    work_pools[body.name] = pool
    logger.info("Created work pool: %s (%s)", body.name, pool_id)
    return pool


@app.get("/api/work_pools/")
async def list_work_pools() -> List[Dict[str, Any]]:
    return list(work_pools.values())


@app.get("/api/work_pools/{name}")
async def get_work_pool(name: str) -> Dict[str, Any]:
    if name not in work_pools:
        raise HTTPException(404, f"Work pool '{name}' not found")
    return work_pools[name]


# ---------------------------------------------------------------------------
# Deployment endpoints
# ---------------------------------------------------------------------------
@app.post("/api/deployments/")
async def create_deployment(body: DeploymentCreate) -> Dict[str, Any]:
    if body.work_pool_name not in work_pools:
        raise HTTPException(
            404,
            f"Work pool '{body.work_pool_name}' not found. "
            f"Available: {list(work_pools.keys())}",
        )
    dep_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    dep = {
        "id": dep_id,
        "name": body.name,
        "flow_name": body.flow_name,
        "work_pool_name": body.work_pool_name,
        "parameters": body.parameters or {},
        "tags": body.tags or [],
        "description": body.description,
        "schedule": body.schedule,
        "flow_definition": body.flow_definition,
        "status": "READY",
        "created": now,
        "updated": now,
    }
    deployments[dep_id] = dep
    work_pools[body.work_pool_name]["pending_work"] += 1
    logger.info("Created deployment: %s -> pool %s", body.name, body.work_pool_name)
    return dep


@app.get("/api/deployments/{dep_id}")
async def get_deployment(dep_id: str) -> Dict[str, Any]:
    if dep_id not in deployments:
        raise HTTPException(404, f"Deployment '{dep_id}' not found")
    return deployments[dep_id]


# ---------------------------------------------------------------------------
# Flow run endpoints
# ---------------------------------------------------------------------------
@app.post("/api/deployments/{dep_id}/create_flow_run")
async def create_flow_run(dep_id: str, body: FlowRunCreate) -> Dict[str, Any]:
    if dep_id not in deployments:
        raise HTTPException(404, f"Deployment '{dep_id}' not found")
    dep = deployments[dep_id]
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    run = {
        "id": run_id,
        "deployment_id": dep_id,
        "flow_name": dep["flow_name"],
        "work_pool_name": dep["work_pool_name"],
        "parameters": {**dep["parameters"], **(body.parameters or {})},
        "tags": list(set((dep["tags"] or []) + (body.tags or []))),
        "state": {
            "type": FlowRunState.SCHEDULED.value,
            "message": "Run scheduled",
            "timestamp": now,
        },
        "flow_definition": dep.get("flow_definition"),
        "task_runs": [],
        "created": now,
        "updated": now,
        "start_time": None,
        "end_time": None,
    }
    flow_runs[run_id] = run
    logger.info("Created flow run: %s for deployment %s", run_id, dep_id)
    # Simulate async execution start
    asyncio.create_task(_simulate_flow_execution(run_id))
    return run


@app.get("/api/flow_runs/{run_id}")
async def get_flow_run(run_id: str) -> Dict[str, Any]:
    if run_id not in flow_runs:
        raise HTTPException(404, f"Flow run '{run_id}' not found")
    return flow_runs[run_id]


@app.get("/api/flow_runs/")
async def list_flow_runs() -> List[Dict[str, Any]]:
    return list(flow_runs.values())


@app.post("/api/flow_runs/{run_id}/set_state")
async def set_flow_run_state(run_id: str, body: StateUpdate) -> Dict[str, Any]:
    if run_id not in flow_runs:
        raise HTTPException(404, f"Flow run '{run_id}' not found")
    now = datetime.now(timezone.utc).isoformat()
    flow_runs[run_id]["state"] = {
        "type": body.type,
        "message": body.message or "",
        "timestamp": now,
    }
    flow_runs[run_id]["updated"] = now
    if body.type == FlowRunState.COMPLETED.value:
        flow_runs[run_id]["end_time"] = now
    return flow_runs[run_id]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "version": "mock-0.1.0",
        "work_pools": len(work_pools),
        "deployments": len(deployments),
        "flow_runs": len(flow_runs),
    }


# ---------------------------------------------------------------------------
# Simulation helper
# ---------------------------------------------------------------------------
async def _simulate_flow_execution(run_id: str) -> None:
    """Simulate a flow progressing through PENDING -> RUNNING -> COMPLETED."""
    await asyncio.sleep(0.2)
    run = flow_runs.get(run_id)
    if not run:
        return
    now = datetime.now(timezone.utc).isoformat()
    run["state"] = {"type": "PENDING", "message": "Waiting for worker", "timestamp": now}
    run["updated"] = now

    await asyncio.sleep(0.3)
    now = datetime.now(timezone.utc).isoformat()
    run["state"] = {"type": "RUNNING", "message": "Executing tasks", "timestamp": now}
    run["start_time"] = now
    run["updated"] = now

    # Simulate individual task runs if flow_definition has tasks
    flow_def = run.get("flow_definition") or {}
    tasks = flow_def.get("tasks", [])
    for task_def in tasks:
        task_run_id = str(uuid.uuid4())
        task_now = datetime.now(timezone.utc).isoformat()
        tr = {
            "id": task_run_id,
            "flow_run_id": run_id,
            "task_key": task_def.get("task_key", "unknown"),
            "name": task_def.get("name", "unnamed_task"),
            "mcp_tool": task_def.get("mcp_tool", ""),
            "state": {"type": "COMPLETED", "timestamp": task_now},
            "created": task_now,
        }
        task_runs[task_run_id] = tr
        run["task_runs"].append(task_run_id)
        await asyncio.sleep(0.1)

    await asyncio.sleep(0.2)
    now = datetime.now(timezone.utc).isoformat()
    run["state"] = {"type": "COMPLETED", "message": "All tasks finished", "timestamp": now}
    run["end_time"] = now
    run["updated"] = now
    pool_name = run.get("work_pool_name", "")
    if pool_name in work_pools:
        work_pools[pool_name]["pending_work"] = max(
            0, work_pools[pool_name]["pending_work"] - 1
        )
    logger.info("Flow run %s completed", run_id)
