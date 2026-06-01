#!/bin/bash
# Run the Datadog log generator
# Usage:
#   ./run.sh              # Run for 3 minutes (default)
#   ./run.sh 10           # Run for 10 minutes
#   ./run.sh oneshot      # Send one batch and exit
#   ./run.sh continuous   # Run continuously until Ctrl+C

if [ -z "$DD_API_KEY" ]; then
  echo "ERROR: DD_API_KEY is not set. export DD_API_KEY=... before running."
  exit 1
fi

MODE="${1:-3}"

case "$MODE" in
  oneshot)
    echo "Sending one batch of logs..."
    python3 generator.py --one-shot --verbose
    ;;
  continuous)
    echo "Running continuously (Ctrl+C to stop)..."
    python3 generator.py --verbose
    ;;
  *)
    echo "Running for ${MODE} minutes..."
    python3 generator.py --duration "$MODE" --verbose
    ;;
esac
