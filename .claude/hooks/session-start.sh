#!/bin/bash
set -euo pipefail

# SessionStart hook for plugin-orchestrator
# Validates environment and runs test suite

echo "🚀 Starting plugin-orchestrator session..."

# Verify Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not found"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python $PYTHON_VERSION available"

# Run test suite to verify environment
echo "🧪 Running test suite..."
if python3 -m unittest discover -s tests -q; then
    echo "✅ All tests passed"
else
    echo "❌ Tests failed"
    exit 1
fi

echo "✅ Session ready - plugin-orchestrator is operational"
