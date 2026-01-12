#!/bin/bash

# Build and Test Script for OpenVINO Detection MCP Server Dockerfiles
# This script builds all Dockerfile variants and runs basic tests

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
IMAGE_NAME="openvino-detection"
TEST_PORT=8006
TIMEOUT=120

echo "================================================"
echo "OpenVINO Detection MCP Server - Build & Test"
echo "================================================"
echo ""

# Function to print colored messages
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Function to check if a port is available
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        print_error "Port $port is already in use"
        return 1
    fi
    return 0
}

# Function to wait for server to be ready
wait_for_server() {
    local container_name=$1
    local max_wait=$TIMEOUT
    local waited=0
    
    print_info "Waiting for server to be ready (max ${max_wait}s)..."
    
    while [ $waited -lt $max_wait ]; do
        if curl -s http://localhost:$TEST_PORT/mcp > /dev/null 2>&1; then
            print_info "Server is ready!"
            return 0
        fi
        sleep 5
        waited=$((waited + 5))
        echo -n "."
    done
    
    echo ""
    print_error "Server failed to start within ${max_wait}s"
    docker logs "$container_name" 2>&1 | tail -50
    return 1
}

# Function to test server functionality
test_server() {
    local container_name=$1
    
    print_info "Testing server functionality..."
    
    # Test health endpoint
    print_info "Testing health endpoint..."
    if ! curl -s http://localhost:$TEST_PORT/mcp > /dev/null; then
        print_error "Health check failed"
        return 1
    fi
    print_info "Health check passed"
    
    # Test that server is responding
    local response=$(curl -s http://localhost:$TEST_PORT/mcp)
    if [ -z "$response" ]; then
        print_error "Server returned empty response"
        return 1
    fi
    print_info "Server response test passed"
    
    return 0
}

# Function to cleanup containers
cleanup() {
    local container_name=$1
    print_info "Cleaning up container: $container_name"
    docker stop "$container_name" 2>/dev/null || true
    docker rm "$container_name" 2>/dev/null || true
}

# Function to build and test a Dockerfile
build_and_test() {
    local dockerfile=$1
    local tag=$2
    local variant=$3
    
    echo ""
    echo "================================================"
    print_info "Building and testing: $dockerfile"
    echo "================================================"
    
    # Build image
    print_info "Building image: ${IMAGE_NAME}:${tag}"
    if ! docker build -f "$dockerfile" -t "${IMAGE_NAME}:${tag}" .; then
        print_error "Build failed for $dockerfile"
        return 1
    fi
    print_info "Build successful"
    
    # Check port availability
    if ! check_port $TEST_PORT; then
        print_error "Cannot run test - port $TEST_PORT is in use"
        return 1
    fi
    
    # Run container
    local container_name="${IMAGE_NAME}-test-${variant}"
    cleanup "$container_name"
    
    print_info "Starting container: $container_name"
    if ! docker run -d \
        --name "$container_name" \
        -p $TEST_PORT:8006 \
        "${IMAGE_NAME}:${tag}"; then
        print_error "Failed to start container"
        return 1
    fi
    
    # Wait for server and test
    local test_result=0
    if wait_for_server "$container_name"; then
        if test_server "$container_name"; then
            print_info "All tests passed for $dockerfile"
        else
            print_error "Tests failed for $dockerfile"
            test_result=1
        fi
    else
        print_error "Server startup failed for $dockerfile"
        test_result=1
    fi
    
    # Show image size
    local image_size=$(docker images "${IMAGE_NAME}:${tag}" --format "{{.Size}}")
    print_info "Image size: $image_size"
    
    # Cleanup
    cleanup "$container_name"
    
    return $test_result
}

# Main execution
main() {
    local overall_result=0
    
    print_info "Starting build and test process..."
    
    # Build and test Ubuntu variant
    if [ -f "Dockerfile.ubuntu" ]; then
        if ! build_and_test "Dockerfile.ubuntu" "ubuntu" "ubuntu"; then
            overall_result=1
        fi
    else
        print_warning "Dockerfile.ubuntu not found, skipping"
    fi
    
    # Build and test RHEL variant
    if [ -f "Dockerfile.rhel" ]; then
        if ! build_and_test "Dockerfile.rhel" "rhel" "rhel"; then
            overall_result=1
        fi
    else
        print_warning "Dockerfile.rhel not found, skipping"
    fi
    
    # Summary
    echo ""
    echo "================================================"
    echo "Build and Test Summary"
    echo "================================================"
    
    if [ $overall_result -eq 0 ]; then
        print_info "All builds and tests completed successfully!"
        echo ""
        print_info "Available images:"
        docker images "${IMAGE_NAME}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}"
    else
        print_error "Some builds or tests failed"
        exit 1
    fi
}

# Run main function
main
