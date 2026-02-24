# Prefect Orchestration Mock

Last updated: 2026-02-24

Mock Prefect API server and MCP tool integration example demonstrating
how to map MCP tools to Prefect tasks and orchestrate them as flows
submitted to work pools.

## Architecture

```
                        +---------------------------+
                        |   Atlas UI / LLM Agent    |
                        +---------------------------+
                                    |
               +--------------------+--------------------+
               |                                         |
  +------------v-----------+             +---------------v-----------+
  | prefect_planner (MCP)  |             | prefect_runner (MCP)      |
  |                        |             |                           |
  | - Reads _mcp_data      |             | - create_work_pool        |
  | - Maps tools to tasks  |  flow_def   | - submit_flow             |
  | - Plans flow via LLM   +------------>| - get_run_status          |
  | - Generates Python     |             | - list_work_pools         |
  +------------------------+             +-------------+-------------+
                                                       |
                                          HTTP REST    |
                                                       v
                                         +-------------+-------------+
                                         | Mock Prefect API Server   |
                                         | (mocks/prefect-mock)      |
                                         |                           |
                                         | /api/work_pools/          |
                                         | /api/deployments/         |
                                         | /api/flow_runs/           |
                                         +---------------------------+
```

## Components

### 1. Mock Prefect Server (`prefect_mock_server.py`)

A FastAPI app that simulates the Prefect REST API.  Stores work pools,
deployments, and flow runs in memory.  Simulates async flow execution
(SCHEDULED -> PENDING -> RUNNING -> COMPLETED).

```bash
cd mocks/prefect-orchestration-mock
python main.py --port 4220
```

### 2. Prefect Planner MCP (`atlas/mcp/prefect_planner/main.py`)

An MCP tool server that:
- Receives `_mcp_data` with all available MCP tools
- Maps each tool to a Prefect `@task` definition
- Uses LLM sampling to plan task ordering/dependencies
- Returns a flow definition JSON and generated Python code

### 3. Prefect Runner MCP (`atlas/mcp/prefect_runner/main.py`)

An MCP tool server that:
- Creates work pools on the Prefect server
- Deploys flow definitions to a work pool
- Starts flow runs and monitors status

## Quick Start

```bash
# 1. Start the mock Prefect server
cd mocks/prefect-orchestration-mock
python main.py &

# 2. Run the example script to see the full flow
python example_usage.py
```

## MCP Tool -> Prefect Task Mapping

Each MCP tool is mapped to a Prefect task following this pattern:

```
MCP Tool:  server_name / tool_name (with parameters)
    |
    v
Prefect Task:
    @task(name="server_toolName")
    def task_server_toolname(param1: str, param2: int = None):
        """Calls MCP tool: server_toolName"""
        return call_mcp_tool("server", "toolName", locals())
```

The planner assembles these tasks into a `@flow` with dependency edges:

```python
@flow(name="data_analysis_flow")
def data_analysis_flow():
    results = {}
    results["db_query"] = task_db_select_users(department="Engineering")
    results["calc_avg"] = task_calculator_evaluate(
        expression=results["db_query"]
    )
    results["report"] = task_csv_reporter_create(data=results["calc_avg"])
    return results
```

## Configuration

Add to your `mcp.json`:

```json
{
  "prefect_planner": {
    "command": ["python", "mcp/prefect_planner/main.py"],
    "cwd": "atlas",
    "groups": ["users"]
  },
  "prefect_runner": {
    "command": ["python", "mcp/prefect_runner/main.py"],
    "cwd": "atlas",
    "groups": ["users"],
    "env": {
      "PREFECT_API_URL": "http://127.0.0.1:4220"
    }
  }
}
```

Set `PREFECT_API_URL` to point at a real Prefect server for production use.
