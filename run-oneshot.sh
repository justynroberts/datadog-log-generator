#!/bin/bash
# Quick one-shot: send a single batch of logs and exit
if [ -z "$DD_API_KEY" ]; then
  echo "ERROR: DD_API_KEY is not set. export DD_API_KEY=... before running."
  exit 1
fi
python3 generator.py --one-shot
