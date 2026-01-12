#!/usr/bin/env python3
"""
Validation script for OpenVINO Object Detection MCP Server
Checks that all required files and structure are present without requiring full dependencies.
"""

import os
import sys
import json
from pathlib import Path

def check_file_exists(file_path, description):
    """Check if a file exists and report status"""
    if os.path.exists(file_path):
        print(f"✓ {description}: {file_path}")
        return True
    else:
        print(f"✗ {description}: {file_path} - MISSING")
        return False

def check_executable(file_path, description):
    """Check if a file exists and is executable"""
    if os.path.exists(file_path) and os.access(file_path, os.X_OK):
        print(f"✓ {description}: {file_path}")
        return True
    else:
        print(f"✗ {description}: {file_path} - NOT EXECUTABLE")
        return False

def check_directory_exists(dir_path, description):
    """Check if a directory exists"""
    if os.path.isdir(dir_path):
        print(f"✓ {description}: {dir_path}")
        return True
    else:
        print(f"✗ {description}: {dir_path} - MISSING")
        return False

def check_json_valid(file_path, description):
    """Check if a JSON file is valid"""
    try:
        with open(file_path, 'r') as f:
            json.load(f)
        print(f"✓ {description}: {file_path}")
        return True
    except Exception as e:
        print(f"✗ {description}: {file_path} - INVALID: {e}")
        return False

def main():
    """Main validation function"""
    print("=" * 60)
    print("OpenVINO Object Detection MCP Server - Structure Validation")
    print("=" * 60)
    print()
    
    # Get the script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    all_checks_passed = True
    
    # Core files
    print("Core Files:")
    all_checks_passed &= check_file_exists("main.py", "Main server script")
    all_checks_passed &= check_file_exists("requirements.txt", "Requirements file")
    all_checks_passed &= check_file_exists("README.md", "README documentation")
    print()
    
    # Docker files
    print("Docker Files:")
    all_checks_passed &= check_file_exists("Dockerfile.ubuntu", "Ubuntu Dockerfile")
    all_checks_passed &= check_file_exists("Dockerfile.rhel", "RHEL Dockerfile")
    all_checks_passed &= check_file_exists("docker-compose.yml", "Docker Compose file")
    print()
    
    # Scripts
    print("Scripts:")
    all_checks_passed &= check_executable("run.sh", "Run script")
    all_checks_passed &= check_executable("build_and_test_dockerfiles.sh", "Build test script")
    print()
    
    # Configuration
    print("Configuration:")
    all_checks_passed &= check_json_valid("mcp-config.json", "MCP config")
    print()
    
    # Documentation
    print("Documentation:")
    all_checks_passed &= check_file_exists("QUICKSTART.md", "Quick start guide")
    all_checks_passed &= check_file_exists("DOCKER_K8S_DEPLOYMENT.md", "Deployment guide")
    all_checks_passed &= check_file_exists("BUILD_NOTES.md", "Build notes")
    print()
    
    # Helm chart
    print("Helm Chart:")
    all_checks_passed &= check_directory_exists("helm/openvino-server", "Helm chart directory")
    all_checks_passed &= check_file_exists("helm/openvino-server/Chart.yaml", "Chart.yaml")
    all_checks_passed &= check_file_exists("helm/openvino-server/values.yaml", "values.yaml")
    all_checks_passed &= check_file_exists("helm/openvino-server/values-dev.yaml", "values-dev.yaml")
    all_checks_passed &= check_file_exists("helm/openvino-server/values-prod.yaml", "values-prod.yaml")
    all_checks_passed &= check_directory_exists("helm/openvino-server/templates", "Templates directory")
    print()
    
    # Helm templates
    print("Helm Templates:")
    templates = [
        "deployment.yaml", "service.yaml", "ingress.yaml", "hpa.yaml",
        "serviceaccount.yaml", "configmap.yaml", "secret.yaml", "pvc.yaml",
        "_helpers.tpl", "NOTES.txt"
    ]
    for template in templates:
        all_checks_passed &= check_file_exists(
            f"helm/openvino-server/templates/{template}",
            f"Template: {template}"
        )
    print()
    
    # Check main.py structure
    print("Code Structure Validation:")
    try:
        with open("main.py", 'r') as f:
            content = f.read()
            
        # Check for key components
        checks = [
            ("FastMCP import", "from fastmcp import FastMCP" in content),
            ("MCP server initialization", "mcp = FastMCP" in content),
            ("detect_objects tool", "@mcp.tool" in content and "def detect_objects" in content),
            ("detect_objects_base64 tool", "def detect_objects_base64" in content),
            ("list_available_models tool", "def list_available_models" in content),
            ("get_class_labels tool", "def get_class_labels" in content),
            ("HTTP transport support", '"http"' in content or 'transport="http"' in content),
            ("Command line args", "argparse" in content),
        ]
        
        for description, passed in checks:
            if passed:
                print(f"✓ {description}")
            else:
                print(f"✗ {description} - NOT FOUND")
                all_checks_passed = False
        
    except Exception as e:
        print(f"✗ Could not validate main.py: {e}")
        all_checks_passed = False
    
    print()
    print("=" * 60)
    if all_checks_passed:
        print("✓ All validation checks passed!")
        print("=" * 60)
        return 0
    else:
        print("✗ Some validation checks failed!")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
