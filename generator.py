#!/usr/bin/env python3
"""
Datadog Log Generator - Generate realistic logs for multiple services
"""

import os
import sys
import json
import yaml
import random
import requests
import time
import argparse
from datetime import datetime, timezone
from typing import Dict, List, Any
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatadogLogGenerator:
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.dd_api_key = self._get_api_key()
        self.dd_site = self.config['datadog'].get('site', 'datadoghq.com')
        self.dd_url = f"https://http-intake.logs.{self.dd_site}/v1/input"
        self.stats = {
            'sent': 0,
            'failed': 0,
            'by_service': {}
        }
        
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded configuration from {config_path}")
            return config
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            sys.exit(1)
            
    def _get_api_key(self) -> str:
        """Get Datadog API key from config or environment"""
        api_key = self.config['datadog']['api_key']
        
        # Support environment variable substitution
        if api_key.startswith('${') and api_key.endswith('}'):
            env_var = api_key[2:-1]
            api_key = os.getenv(env_var)
            
        if not api_key:
            logger.error("Datadog API key not found. Set DD_API_KEY environment variable.")
            sys.exit(1)
            
        return api_key
        
    def _generate_log_entry(self, service_name: str, service_config: Dict) -> Dict:
        """Generate a single log entry based on service configuration"""
        
        # Select log pattern based on weights
        patterns = service_config['log_patterns']
        weights = [p['weight'] for p in patterns]
        pattern = random.choices(patterns, weights=weights)[0]
        
        # Select random template and hostname
        template = random.choice(pattern['templates'])
        hostname = random.choice(service_config['hostnames'])
        
        # Generate attributes
        attributes = {}
        for key, values in pattern.get('attributes', {}).items():
            if key in template:  # Only include if used in template
                value = random.choice(values)
                attributes[key] = value
        
        # Replace template placeholders
        message = template
        for key, value in attributes.items():
            placeholder = f"{{{key}}}"
            if placeholder in message:
                message = message.replace(placeholder, str(value))
        
        # Build log entry
        log_entry = {
            "ddsource": service_name,
            "ddtags": ",".join(service_config['tags']),
            "hostname": hostname,
            "service": service_name,
            "level": pattern['level'],
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            **attributes
        }
        
        return log_entry
        
    def _send_log(self, log_entry: Dict) -> bool:
        """Send log entry to Datadog"""
        try:
            response = requests.post(
                self.dd_url,
                headers={
                    "Content-Type": "application/json",
                    "DD-API-KEY": self.dd_api_key
                },
                data=json.dumps(log_entry),
                timeout=5
            )
            
            # Accept both 200 and 202 as success
            if response.status_code in (200, 202):
                return True
            else:
                logger.warning(f"Failed to send log: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending log: {e}")
            return False
            
    def generate_logs(self, duration_minutes: int = None, one_shot: bool = False):
        """Generate logs continuously or for specified duration"""
        
        enabled_services = {
            name: config 
            for name, config in self.config['services'].items() 
            if config.get('enabled', True)
        }
        
        if not enabled_services:
            logger.error("No enabled services found in configuration")
            return
            
        logger.info(f"Starting log generation for {len(enabled_services)} services")
        for service_name in enabled_services.keys():
            logger.info(f"  - {service_name}")
            self.stats['by_service'][service_name] = {'sent': 0, 'failed': 0}
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60) if duration_minutes else None
        
        try:
            while True:
                cycle_start = time.time()
                
                # Generate logs for each enabled service
                for service_name, service_config in enabled_services.items():
                    rate = service_config.get('rate_per_minute', 10)
                    
                    if one_shot:
                        # One-shot mode: send exactly the rate per minute
                        logs_to_send = rate
                    else:
                        # Continuous mode: distribute across the minute
                        logs_to_send = 1  # Send one per service per cycle
                    
                    for _ in range(logs_to_send):
                        log_entry = self._generate_log_entry(service_name, service_config)
                        
                        if self._send_log(log_entry):
                            self.stats['sent'] += 1
                            self.stats['by_service'][service_name]['sent'] += 1
                            logger.debug(f"[{service_name}] {log_entry['level']}: {log_entry['message']}")
                        else:
                            self.stats['failed'] += 1
                            self.stats['by_service'][service_name]['failed'] += 1
                
                # Print stats every 60 seconds
                if int(time.time()) % 60 == 0:
                    self._print_stats()
                
                # Check if we should stop
                if one_shot:
                    break
                    
                if end_time and time.time() >= end_time:
                    logger.info(f"Duration limit reached ({duration_minutes} minutes)")
                    break
                
                # Calculate sleep time to maintain rate
                cycle_duration = time.time() - cycle_start
                sleep_time = max(0, 1 - cycle_duration)  # Aim for 1 second cycles
                time.sleep(sleep_time)
                
        except KeyboardInterrupt:
            logger.info("\nStopping log generation...")
        
        self._print_stats()
        
    def _print_stats(self):
        """Print generation statistics"""
        logger.info("="*60)
        logger.info(f"Total logs sent: {self.stats['sent']}")
        logger.info(f"Total logs failed: {self.stats['failed']}")
        logger.info("-"*60)
        for service_name, stats in self.stats['by_service'].items():
            logger.info(f"  {service_name}: {stats['sent']} sent, {stats['failed']} failed")
        logger.info("="*60)


def main():
    parser = argparse.ArgumentParser(
        description='Generate realistic logs for Datadog',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run continuously
  python log_generator.py
  
  # Run for 10 minutes
  python log_generator.py --duration 10
  
  # Send one batch of logs
  python log_generator.py --one-shot
  
  # Use custom config
  python log_generator.py --config /path/to/config.yaml
        """
    )
    
    parser.add_argument(
        '--config',
        default='config/services.yaml',
        help='Path to configuration file (default: config/services.yaml)'
    )
    
    parser.add_argument(
        '--duration',
        type=int,
        help='Duration in minutes (default: run continuously)'
    )
    
    parser.add_argument(
        '--one-shot',
        action='store_true',
        help='Send one batch of logs and exit'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Initialize generator
    generator = DatadogLogGenerator(args.config)
    
    # Generate logs
    generator.generate_logs(
        duration_minutes=args.duration,
        one_shot=args.one_shot
    )


if __name__ == '__main__':
    main()
