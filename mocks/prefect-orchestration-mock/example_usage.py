#!/usr/bin/env python3
"""
End-to-end example: MCP tools -> Prefect tasks -> Flow -> Work Pool -> Job.

Demonstrates the full orchestration pipeline without requiring a real
Prefect server or real MCP connections.  Uses the mock Prefect API and
simulated _mcp_data.

Usage:
    # Start the mock server first in another terminal:
    #   python main.py --port 4220
    #
    # Then run this example:
    python example_usage.py

    # Or run standalone (starts mock server in-process):
    python example_usage.py --standalone
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict

import requests

# -- Simulated MCP tool metadata (what Atlas UI injects as _mcp_data) ------
SIMULATED_MCP_DATA: Dict[str, Any] = {
    "available_servers": [
        {
            "server_name": "calculator",
            "description": "Mathematical calculator",
            "tools": [
                {
                    "name": "evaluate",
                    "description": "Evaluate a mathematical expression",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expression": {
                                "type": "string",
                                "description": "Math expression to evaluate",
                            }
                        },
                        "required": ["expression"],
                    },
                }
            ],
        },
        {
            "server_name": "csv_reporter",
            "description": "CSV report generator",
            "tools": [
                {
                    "name": "create_report",
                    "description": "Create a CSV report from data",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "Report title",
                            },
                            "data": {
                                "type": "string",
                                "description": "Data to include in report",
                            },
                            "format": {
                                "type": "string",
                                "description": "Output format",
                            },
                        },
                        "required": ["title", "data"],
                    },
                }
            ],
        },
        {
            "server_name": "database",
            "description": "Database query tool",
            "tools": [
                {
                    "name": "select_users",
                    "description": "Query users from the database",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "department": {
                                "type": "string",
                                "description": "Filter by department",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Max results",
                            },
                        },
                        "required": [],
                    },
                }
            ],
        },
    ]
}

PREFECT_API = "http://127.0.0.1:4220"


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def run_example() -> None:
    # ------------------------------------------------------------------
    # Step 1: Map MCP tools to Prefect tasks (what the planner does)
    # ------------------------------------------------------------------
    section("Step 1: Map MCP tools to Prefect task definitions")

    # Import the planner's mapping logic directly
    sys.path.insert(0, "../../atlas/mcp/prefect_planner")
    from main import map_all_tools  # noqa: E402

    task_mappings = map_all_tools(SIMULATED_MCP_DATA)
    print(f"Mapped {len(task_mappings)} MCP tools to Prefect tasks:\n")
    for mapping in task_mappings:
        print(f"  Task key:   {mapping['task_key']}")
        print(f"  MCP server: {mapping['mcp_server']}")
        print(f"  Parameters: {list(mapping['parameters'].keys())}")
        print(f"  Python stub:\n    {mapping['python_stub'].replace(chr(10), chr(10) + '    ')}")
        print()

    # ------------------------------------------------------------------
    # Step 2: Build a flow definition (normally done by LLM sampling)
    # ------------------------------------------------------------------
    section("Step 2: Build a Prefect flow definition")

    flow_definition = {
        "flow_name": "user_report_flow",
        "description": "Query users from database, calculate stats, and generate a CSV report",
        "tasks": [
            {
                "task_key": "database_select_users",
                "depends_on": [],
                "parameters": {"department": "Engineering", "limit": 10},
            },
            {
                "task_key": "calculator_evaluate",
                "depends_on": ["database_select_users"],
                "parameters": {"expression": "{{database_select_users}}"},
            },
            {
                "task_key": "csv_reporter_create_report",
                "depends_on": ["calculator_evaluate"],
                "parameters": {
                    "title": "Engineering Team Report",
                    "data": "{{calculator_evaluate}}",
                },
            },
        ],
    }

    print("Flow definition:")
    print(json.dumps(flow_definition, indent=2))

    # ------------------------------------------------------------------
    # Step 3: Generate runnable Python code
    # ------------------------------------------------------------------
    section("Step 3: Generate Prefect Python code")

    from main import _generate_flow_python  # noqa: E402

    python_code = _generate_flow_python(flow_definition, task_mappings)
    print(python_code)

    # ------------------------------------------------------------------
    # Step 4: Create a work pool via the mock Prefect API
    # ------------------------------------------------------------------
    section("Step 4: Create a Prefect work pool")

    pool_resp = requests.post(f"{PREFECT_API}/api/work_pools/", json={
        "name": "mcp-tasks-pool",
        "type": "process",
        "description": "Work pool for MCP-derived Prefect tasks",
        "concurrency_limit": 4,
    }, timeout=10)

    if pool_resp.status_code == 409:
        print("Work pool 'mcp-tasks-pool' already exists, reusing.")
        pool_data = requests.get(
            f"{PREFECT_API}/api/work_pools/mcp-tasks-pool", timeout=10
        ).json()
    else:
        pool_resp.raise_for_status()
        pool_data = pool_resp.json()

    print(f"Work pool: {pool_data['name']}")
    print(f"  Type: {pool_data['type']}")
    print(f"  Status: {pool_data['status']}")
    print(f"  Concurrency limit: {pool_data['concurrency_limit']}")

    # ------------------------------------------------------------------
    # Step 5: Deploy the flow and start a run
    # ------------------------------------------------------------------
    section("Step 5: Deploy flow and start a run on the work pool")

    dep_resp = requests.post(f"{PREFECT_API}/api/deployments/", json={
        "name": "user_report_deployment",
        "flow_name": flow_definition["flow_name"],
        "work_pool_name": "mcp-tasks-pool",
        "parameters": {},
        "tags": ["mcp", "example"],
        "description": flow_definition["description"],
        "flow_definition": flow_definition,
    }, timeout=10)
    dep_resp.raise_for_status()
    dep_data = dep_resp.json()
    dep_id = dep_data["id"]
    print(f"Deployment created: {dep_id}")
    print(f"  Name: {dep_data['name']}")
    print(f"  Pool: {dep_data['work_pool_name']}")

    run_resp = requests.post(
        f"{PREFECT_API}/api/deployments/{dep_id}/create_flow_run",
        json={"tags": ["run-1"]},
        timeout=10,
    )
    run_resp.raise_for_status()
    run_data = run_resp.json()
    run_id = run_data["id"]
    print(f"\nFlow run started: {run_id}")
    print(f"  Initial state: {run_data['state']['type']}")

    # ------------------------------------------------------------------
    # Step 6: Poll for completion
    # ------------------------------------------------------------------
    section("Step 6: Poll flow run until completion")

    for attempt in range(20):
        time.sleep(0.3)
        status_resp = requests.get(
            f"{PREFECT_API}/api/flow_runs/{run_id}", timeout=10
        )
        status_resp.raise_for_status()
        status = status_resp.json()
        state = status["state"]["type"]
        print(f"  [{attempt+1}] State: {state} - {status['state'].get('message', '')}")
        if state in ("COMPLETED", "FAILED", "CANCELLED"):
            break

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    section("Summary")
    final = requests.get(f"{PREFECT_API}/api/flow_runs/{run_id}", timeout=10).json()
    print(f"Flow: {final['flow_name']}")
    print(f"State: {final['state']['type']}")
    print(f"Tasks executed: {len(final.get('task_runs', []))}")
    print(f"Start: {final.get('start_time', 'N/A')}")
    print(f"End:   {final.get('end_time', 'N/A')}")
    print("\nWork pool status:")
    pool_final = requests.get(
        f"{PREFECT_API}/api/work_pools/mcp-tasks-pool", timeout=10
    ).json()
    print(f"  Pending work: {pool_final['pending_work']}")
    print("\nDone.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prefect orchestration example")
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="Start mock Prefect server in-process (no separate terminal needed)",
    )
    parser.add_argument("--port", type=int, default=4220)
    args = parser.parse_args()

    global PREFECT_API
    PREFECT_API = f"http://127.0.0.1:{args.port}"

    if args.standalone:
        import threading

        import uvicorn
        from prefect_mock_server import app

        server = uvicorn.Server(uvicorn.Config(
            app, host="127.0.0.1", port=args.port, log_level="warning",
        ))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        time.sleep(0.5)  # wait for server startup
        print(f"Mock Prefect server started on port {args.port}")

    run_example()


if __name__ == "__main__":
    main()
