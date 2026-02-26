"""
Prefect flow that executes user-submitted Python code in a K8s Job container.
Captures stdout/stderr and reports results through Prefect's state system.
"""

import io
import sys
import traceback

from prefect import flow, get_run_logger


MAX_OUTPUT_CHARS = 100_000


@flow(name="python-runner", log_prints=True)
def run_python_code(code: str) -> dict:
    """Execute Python code and capture output.

    Args:
        code: Python source code to execute.

    Returns:
        Dict with stdout, stderr, and success status.
    """
    logger = get_run_logger()
    logger.info("Executing user-submitted Python code (%d chars)", len(code))

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    old_stdout = sys.stdout
    old_stderr = sys.stderr

    result = {"stdout": "", "stderr": "", "success": False, "error": None}

    try:
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        # Execute in a restricted namespace (no access to this module's internals)
        exec_globals = {"__builtins__": __builtins__}
        exec(code, exec_globals)  # noqa: S102 - intentional code execution

        result["success"] = True
    except Exception:
        result["error"] = traceback.format_exc()
        stderr_capture.write(traceback.format_exc())
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    result["stdout"] = stdout_capture.getvalue()[:MAX_OUTPUT_CHARS]
    result["stderr"] = stderr_capture.getvalue()[:MAX_OUTPUT_CHARS]

    if result["success"]:
        logger.info("Code executed successfully.")
    else:
        logger.warning("Code execution failed: %s", result.get("error", "unknown"))

    return result


if __name__ == "__main__":
    # For local testing
    test_code = 'print("Hello from Prefect flow runner!")'
    output = run_python_code(test_code)
    print(f"Result: {output}")
