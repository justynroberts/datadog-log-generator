#!/bin/bash
# Run continuously until Ctrl+C
if [ -z "$DD_API_KEY" ]; then
  echo "ERROR: DD_API_KEY is not set. export DD_API_KEY=... before running."
  exit 1
fi
echo "Running continuously (Ctrl+C to stop)..."
python3 generator.py --verbose
