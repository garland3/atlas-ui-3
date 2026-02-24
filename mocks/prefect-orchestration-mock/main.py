#!/usr/bin/env python3
"""
Entry point for the Mock Prefect API Server.

Usage:
    python main.py                   # default port 4220
    python main.py --port 4220
    python main.py --host 0.0.0.0
"""

from __future__ import annotations

import argparse
import logging

import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock Prefect API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=4220, help="Bind port (default: 4220)")
    args = parser.parse_args()

    logging.getLogger(__name__).info(
        "Starting Mock Prefect server on http://%s:%d", args.host, args.port
    )
    uvicorn.run(
        "prefect_mock_server:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
