#!/bin/bash

# OpenVINO Object Detection MCP Server Runner
# This script starts the OpenVINO MCP server with the appropriate configuration.

set -e

echo "🚀 Starting OpenVINO Object Detection MCP Server..."

# Change to the script directory
cd "$(dirname "$0")"

# Run the server
python main.py "$@"
