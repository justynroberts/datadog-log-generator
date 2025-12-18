# Datadog Log Generator

A Python tool that generates realistic logs and sends them to Datadog's log intake API. Useful for testing dashboards, alerts, log pipelines, and demonstrations.

## Features

- Configurable services with weighted log patterns
- Realistic log messages with randomized attributes
- Multiple log levels (info, warn, error, debug)
- Continuous or one-shot generation modes
- Per-service rate limiting
- Statistics tracking

## Installation

```bash
pip install pyyaml requests
```

## Configuration

1. Set your Datadog API key:
```bash
export DD_API_KEY=your_api_key_here
```

2. Edit `config/services.yaml` to customize services and log patterns.

### Configuration Structure

```yaml
datadog:
  api_key: "${DD_API_KEY}"
  site: "datadoghq.com"  # or datadoghq.eu

services:
  my-service:
    enabled: true
    rate_per_minute: 30
    tags:
      - "env:prod"
      - "service:my-service"
    hostnames:
      - "my-service-01"
    log_patterns:
      - level: "info"
        weight: 70
        templates:
          - "Request completed in {duration_ms}ms"
        attributes:
          duration_ms: [45, 150, 300]
```

## Usage

```bash
# Run continuously
python generator.py

# Run for 10 minutes
python generator.py --duration 10

# Send one batch of logs and exit
python generator.py --one-shot

# Use custom config file
python generator.py --config /path/to/config.yaml

# Enable verbose logging
python generator.py --verbose
```

## Included Services

The default configuration includes example services:
- **travelduty** - Travel API service
- **payment-service** - Payment processing
- **notification-worker** - Email/SMS/push notifications
- **api-gateway** - API gateway (disabled by default)

## License

MIT
