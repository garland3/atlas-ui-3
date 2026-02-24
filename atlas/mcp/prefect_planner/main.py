#!/usr/bin/env python3
"""
Prefect Planner MCP Server using FastMCP.

Maps available MCP tools to Prefect task definitions and assembles them
into a Prefect flow.  Uses _mcp_data injection to discover which tools
are available, then uses LLM sampling (ctx.sample) to decide how to
chain them into a directed task graph.

Tools:
    plan_prefect_flow  - Build a Prefect flow definition from MCP tools.
    list_task_mappings - Show how MCP tools map to Prefect tasks.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from fastmcp import Context, FastMCP

mcp = FastMCP("Prefect Planner")


# ---------------------------------------------------------------------------
# Helpers: MCP tool -> Prefect task mapping
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Convert a tool name into a valid Python identifier."""
    slug = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    return slug.strip("_").lower() or "task"


def map_mcp_tool_to_task(server_name: str, tool: Dict[str, Any]) -> Dict[str, Any]:
    """Convert one MCP tool descriptor into a Prefect task definition.

    Returns a dict describing a Prefect @task that, when executed, would
    call the MCP tool via the Atlas CLI or direct MCP client.

    Keys:
        task_key   - unique key (server_toolName)
        name       - human-readable name
        mcp_tool   - fully qualified MCP tool name
        mcp_server - originating MCP server
        parameters - parameter schema from the tool
        python_stub - example Python code for the @task
    """
    tool_name = tool.get("name", "unknown")
    fq_name = f"{server_name}_{tool_name}"
    func_name = f"task_{_slugify(fq_name)}"

    params = tool.get("parameters", {})
    properties = params.get("properties", {})
    required = set(params.get("required", []))

    # Build a parameter signature string (excluding injected params)
    sig_parts: list[str] = []
    for pname, pschema in properties.items():
        if pname.startswith("_"):
            continue
        ptype = pschema.get("type", "Any")
        type_map = {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}
        py_type = type_map.get(ptype, "Any")
        default = "" if pname in required else " = None"
        sig_parts.append(f"{pname}: {py_type}{default}")

    sig = ", ".join(sig_parts)

    python_stub = (
        f"@task(name=\"{fq_name}\")\n"
        f"def {func_name}({sig}):\n"
        f"    \"\"\"Calls MCP tool: {fq_name}\"\"\"\n"
        f"    return call_mcp_tool(\"{server_name}\", \"{tool_name}\", locals())\n"
    )

    return {
        "task_key": fq_name,
        "name": tool.get("description", fq_name)[:80],
        "mcp_tool": fq_name,
        "mcp_server": server_name,
        "parameters": {
            k: v for k, v in properties.items() if not k.startswith("_")
        },
        "required": list(required),
        "python_stub": python_stub,
    }


def map_all_tools(mcp_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Map every tool in _mcp_data to a Prefect task definition."""
    tasks: list[Dict[str, Any]] = []
    for server in mcp_data.get("available_servers", []):
        server_name = server.get("server_name", "unknown")
        for tool in server.get("tools", []):
            tasks.append(map_mcp_tool_to_task(server_name, tool))
    return tasks


# ---------------------------------------------------------------------------
# Flow assembly
# ---------------------------------------------------------------------------

PLANNER_SYSTEM_PROMPT = """\
You are a Prefect workflow planner.  Given a user task and a list of
available MCP-to-Prefect task mappings, produce a JSON object that
defines a Prefect flow.

Output JSON with this schema (no extra text):
{
  "flow_name": "descriptive_flow_name",
  "description": "one-line summary",
  "tasks": [
    {
      "task_key": "<key from the mapping>",
      "depends_on": ["<task_key>", ...],
      "parameters": { "<param>": "<value or {{prev_task_key}}>" }
    }
  ]
}

Rules:
- Only reference task_keys from the provided mappings.
- Order tasks so dependencies run first.
- Use {{task_key}} syntax to reference output of a previous task.
- Keep the flow minimal -- do not add tasks unless they serve the goal.
"""


def _build_flow_prompt(task_desc: str, task_mappings: List[Dict[str, Any]]) -> str:
    """Build the user prompt for the LLM sampling call."""
    mapping_text = json.dumps(
        [
            {
                "task_key": t["task_key"],
                "name": t["name"],
                "parameters": t["parameters"],
                "required": t["required"],
            }
            for t in task_mappings
        ],
        indent=2,
    )
    return (
        f"User task: {task_desc}\n\n"
        f"Available Prefect tasks (mapped from MCP tools):\n{mapping_text}\n\n"
        "Produce the flow JSON."
    )


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Pull the first JSON object from LLM output, ignoring markdown fences."""
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = cleaned.replace("```", "")
    brace_start = cleaned.find("{")
    if brace_start == -1:
        return None
    depth = 0
    for i in range(brace_start, len(cleaned)):
        if cleaned[i] == "{":
            depth += 1
        elif cleaned[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(cleaned[brace_start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool
async def plan_prefect_flow(
    task: str,
    _mcp_data: Optional[Dict[str, Any]] = None,
    username: Optional[str] = None,
    ctx: Context = None,
) -> Dict[str, Any]:
    """Plan a Prefect flow by mapping MCP tools to Prefect tasks.

    Receives metadata about all available MCP tools via _mcp_data,
    maps each tool to a Prefect task definition, then uses LLM
    sampling to determine how to chain them into a flow that
    accomplishes the user's goal.

    Args:
        task: Description of the workflow to accomplish.
        _mcp_data: Automatically injected by Atlas UI with tool metadata.
        username: Authenticated user (automatically injected).

    Returns:
        A dict containing the flow definition, task mappings, and
        generated Python code for the Prefect flow.
    """
    mcp_data = _mcp_data or {}
    task_mappings = map_all_tools(mcp_data)

    if not task_mappings:
        return {
            "results": {
                "success": False,
                "error": "No MCP tools available to map to Prefect tasks.",
            }
        }

    if ctx:
        await ctx.report_progress(
            progress=0, total=3,
            message=f"Mapped {len(task_mappings)} MCP tools to Prefect tasks",
        )

    # Use sampling to plan the flow ordering
    flow_def: Optional[Dict[str, Any]] = None
    if ctx:
        await ctx.report_progress(
            progress=1, total=3,
            message="Asking LLM to plan task ordering and parameters...",
        )
        prompt = _build_flow_prompt(task, task_mappings)
        result = await ctx.sample(
            messages=prompt,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=4000,
        )
        flow_def = _extract_json(result.text or "")

    # Fallback: sequential flow using all tasks
    if flow_def is None:
        flow_def = {
            "flow_name": f"flow_{_slugify(task[:40])}",
            "description": task,
            "tasks": [
                {
                    "task_key": t["task_key"],
                    "depends_on": (
                        [task_mappings[i - 1]["task_key"]] if i > 0 else []
                    ),
                    "parameters": {},
                }
                for i, t in enumerate(task_mappings)
            ],
        }

    # Generate runnable Python code
    python_code = _generate_flow_python(flow_def, task_mappings)

    if ctx:
        await ctx.report_progress(
            progress=3, total=3, message="Flow plan complete."
        )

    return {
        "results": {
            "success": True,
            "flow_definition": flow_def,
            "task_count": len(flow_def.get("tasks", [])),
            "available_mappings": len(task_mappings),
            "python_code": python_code,
            "message": (
                f"Planned flow '{flow_def.get('flow_name', 'unnamed')}' "
                f"with {len(flow_def.get('tasks', []))} tasks."
            ),
        }
    }


@mcp.tool
def list_task_mappings(
    _mcp_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """List how available MCP tools map to Prefect task definitions.

    Shows each MCP tool alongside its generated Prefect @task stub,
    parameters, and task_key for use in flow planning.

    Args:
        _mcp_data: Automatically injected by Atlas UI with tool metadata.

    Returns:
        A dict listing all tool-to-task mappings with Python stubs.
    """
    mcp_data = _mcp_data or {}
    task_mappings = map_all_tools(mcp_data)
    return {
        "results": {
            "success": True,
            "total_mappings": len(task_mappings),
            "mappings": task_mappings,
        }
    }


# ---------------------------------------------------------------------------
# Code generation
# ---------------------------------------------------------------------------

def _generate_flow_python(
    flow_def: Dict[str, Any], task_mappings: List[Dict[str, Any]]
) -> str:
    """Generate a runnable Prefect flow Python script from the plan."""
    mapping_lookup = {t["task_key"]: t for t in task_mappings}
    tasks_in_flow = flow_def.get("tasks", [])

    lines: list[str] = [
        "#!/usr/bin/env python3",
        '"""Auto-generated Prefect flow from MCP tool mappings."""',
        "",
        "from prefect import flow, task",
        "",
        "",
        "def call_mcp_tool(server: str, tool: str, params: dict):",
        '    """Placeholder: call an MCP tool via Atlas CLI or client."""',
        "    import subprocess, json",
        "    cmd = [",
        '        "python", "atlas_chat_cli.py",',
        '        json.dumps(params),',
        '        "--tools", f"{server}_{tool}",',
        "    ]",
        "    result = subprocess.run(cmd, capture_output=True, text=True)",
        "    return result.stdout",
        "",
        "",
    ]

    # Emit @task functions
    emitted: set[str] = set()
    for t in tasks_in_flow:
        key = t["task_key"]
        mapping = mapping_lookup.get(key)
        if mapping and key not in emitted:
            lines.append(mapping["python_stub"])
            lines.append("")
            emitted.add(key)

    # Emit @flow function
    flow_name = flow_def.get("flow_name", "generated_flow")
    lines.append(f'@flow(name="{flow_name}")')
    lines.append(f"def {_slugify(flow_name)}():")
    lines.append(f'    """{flow_def.get("description", "")}"""')
    lines.append("    results = {}")

    for t in tasks_in_flow:
        key = t["task_key"]
        func = f"task_{_slugify(key)}"
        params = t.get("parameters", {})
        # Resolve {{ref}} to results[ref]
        call_args: list[str] = []
        for pname, pval in params.items():
            if isinstance(pval, str) and pval.startswith("{{") and pval.endswith("}}"):
                ref_key = pval[2:-2]
                call_args.append(f'{pname}=results["{ref_key}"]')
            else:
                call_args.append(f"{pname}={pval!r}")
        args_str = ", ".join(call_args)
        lines.append(f'    results["{key}"] = {func}({args_str})')

    lines.append("    return results")
    lines.append("")
    lines.append("")
    lines.append('if __name__ == "__main__":')
    lines.append(f"    {_slugify(flow_name)}()")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(show_banner=False)
