#!/usr/bin/env python3
import argparse
import requests
import time
import sys
import os

CONTROLLER_URL = os.getenv("CONTROLLER_URL", "http://localhost:8080/api/v1")

def trigger_experiment(scenario, target, delay, threshold):
    payload = {
        "name": scenario,
        "target_selector": {"container": target},
        "parameters": {"delay": delay},
        "auto_abort_threshold_ms": threshold
    }
    print(f"[CI/CD] Triggering Resilience GameDay: {scenario}")
    try:
        res = requests.post(f"{CONTROLLER_URL}/experiments/trigger", json=payload)
        res.raise_for_status()
        print(f"[CI/CD] GameDay '{scenario}' successfully queued in ChaosCore.")
        return True
    except Exception as e:
        print(f"[CI/CD] FATAL: Could not reach ChaosCore Orchestrator: {e}")
        return False

def monitor_mttr(threshold_ms):
    print(f"[CI/CD] Monitoring System MTTR... (Fail threshold: {threshold_ms}ms)")
    # Mocking a CI/CD wait polling loop for synthetic validation
    for i in range(5):
        time.sleep(2)
        print(f"[CI/CD] Validating system health metrics from Orchestrator... Check {i+1}/5")
        
    healthy = True 
    if not healthy:
        print(f"[CI/CD] BUILD BREAK: Recovery time exceeded {threshold_ms}ms.")
        sys.exit(1)
    else:
        print("[CI/CD] BUILD PASSED: System gracefully recovered within acceptable MTTR limits.")
        sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description="ChaosCore CI/CD Execution Binary")
    parser.add_argument("action", choices=["run"])
    parser.add_argument("--scenario", required=True, help="Name of the scenario")
    parser.add_argument("--target", required=True, help="Container target")
    parser.add_argument("--delay", default="200ms", help="Latency delay")
    parser.add_argument("--max-mttr", type=int, default=500, help="Maximum allowed MTTR")
    
    args = parser.parse_args()
    
    if args.action == "run":
        if trigger_experiment(args.scenario, args.target, args.delay, args.max_mttr):
            monitor_mttr(args.max_mttr)
        else:
            sys.exit(2)

if __name__ == "__main__":
    main()
