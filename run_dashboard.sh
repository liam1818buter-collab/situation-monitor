#!/bin/bash
# Run the Situation Monitor Dashboard

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Check for Python
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "Error: Python not found"
    exit 1
fi

echo "Starting Situation Monitor Dashboard..."
echo "Dashboard will be available at: http://localhost:8501"
echo ""

# Run Streamlit
$PYTHON -m streamlit run dashboard/app.py --server.port=8501 --server.address=0.0.0.0 "$@"
