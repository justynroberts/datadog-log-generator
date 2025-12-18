# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Datadog Log Generator - A Python tool that generates realistic logs and sends them to Datadog's log intake API. Used for testing dashboards, alerts, and log pipelines.

## Commands

```bash
# Run continuously (logs sent every second per service)
python generator.py

# Run for a specific duration
python generator.py --duration 10

# Send one batch of logs and exit
python generator.py --one-shot

# Use custom config file
python generator.py --config /path/to/config.yaml

# Enable verbose/debug logging
python generator.py --verbose
```

## Dependencies

- Python 3
- `pyyaml` - YAML config parsing
- `requests` - HTTP client for Datadog API

## Configuration

The `DD_API_KEY` environment variable must be set. The config file (`config/services.yaml`) defines:
- Datadog site (datadoghq.com or datadoghq.eu)
- Services with their log patterns, rates, tags, and hostnames
- Log patterns with weighted templates and variable attributes

## Architecture

Single-file application (`generator.py`) with one class:
- `DatadogLogGenerator` - Loads config, generates logs from weighted templates, sends to Datadog HTTP intake API
- Logs are generated per-service at configurable rates with randomized messages from templates
- Template placeholders like `{duration_ms}` are replaced with random values from the `attributes` list
