#!/usr/bin/env python3
"""Simple experiment runner:
- Generates steady load against the gateway
- Calls the controller to stop a target service (injection)
- Measures MTTD (time until health check fails)
- Calls the controller to start the service (rollback)
- Measures MTTR (time until health check recovers)
- Computes a simple degradation factor based on gateway request counter drop

Usage: python scripts/experiment.py --service auth
"""

import argparse
import threading
import time
import requests
import sys
import json


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--service",
        required=False,
        help="Service name to stop/start (auth|data|gateway). Omit when using --scenario for compound faults.",
    )
    p.add_argument(
        "--gateway", default="http://localhost:8001", help="Gateway base URL"
    )
    p.add_argument(
        "--controller", default="http://localhost:8080", help="Controller base URL"
    )
    p.add_argument(
        "--prometheus",
        default="http://localhost:9090",
        help="Prometheus base URL (not strictly required)",
    )
    p.add_argument(
        "--rps", type=int, default=10, help="Requests per second to generate to gateway"
    )
    p.add_argument(
        "--warmup", type=int, default=8, help="Warmup seconds before injection"
    )
    p.add_argument(
        "--duration", type=int, default=30, help="Total seconds to run the experiment"
    )
    p.add_argument("--scenario", help="Path to a compound fault scenario JSON file")
    return p.parse_args()


class Loader(threading.Thread):
    def __init__(self, base_url, rps):
        super().__init__(daemon=True)
        self.base = base_url
        self.rps = rps
        self.running = threading.Event()
        self.running.set()
        self.sent = 0

    def run(self):
        interval = 1.0 / max(1, self.rps)
        while self.running.is_set():
            try:
                requests.get(self.base, timeout=1.0)
            except Exception:
                pass
            self.sent += 1
            time.sleep(interval)

    def stop(self):
        self.running.clear()


def read_counter_from_metrics(url, metric_name):
    try:
        r = requests.get(url + "/metrics", timeout=2.0)
        r.raise_for_status()
        for line in r.text.splitlines():
            if line.startswith(metric_name + " ") or line.startswith(metric_name + "{"):
                parts = line.split()
                if len(parts) >= 2:
                    return float(parts[-1])
    except Exception:
        return None
    return None


def health_ok(url):
    try:
        r = requests.get(url + "/health", timeout=1.0)
        return r.status_code == 200
    except Exception:
        return False


def main():
    args = parse_args()
    scenario_cfg = None
    if not args.service and not args.scenario:
        print("Error: Must provide either --service or --scenario")
        sys.exit(1)

    metric_name = (
        f"{args.service}_requests_total"
        if args.service != "gateway"
        else "gateway_requests_total"
    )

    loader = Loader(args.gateway, args.rps)
    print("Starting loader ->", args.gateway, f"@ {args.rps} rps")
    loader.start()

    print(f"Warming up for {args.warmup}s...")
    time.sleep(args.warmup)

    before = read_counter_from_metrics(args.gateway, "gateway_requests_total") or 0.0
    t_before = time.time()
    print("Baseline gateway_requests_total:", before)

    # Inject: either simple service stop or compound scenario
    if args.scenario:
        # Load scenario JSON
        with open(args.scenario, "r", encoding="utf-8") as f:
            scenario_cfg = json.load(f)
        print("Injecting compound scenario")
        inject = requests.post(f"{args.controller}/inject/compound", json=scenario_cfg)
        print("Compound injection response:", inject.status_code, inject.text[:200])
        exp_duration = scenario_cfg.get("duration", args.duration)
    else:
        print("Injecting: stop", args.service)
        inject = requests.post(
            f"{args.controller}/inject/stop", json={"services": [args.service]}
        )
        print("Controller response:", inject.status_code, inject.text[:200])
        exp_duration = args.duration

    # MTTD: time until health fails (only for simple service stop)
    if not args.scenario:
        start_inj = time.time()
        mttd = None
        timeout = 30
        for i in range(timeout):
            if not health_ok(
                f"http://localhost:{8000 + (1 if args.service == 'gateway' else (2 if args.service == 'auth' else 3))}"
            ):
                mttd = time.time() - start_inj
                break
            time.sleep(1)

        if mttd is None:
            print("MTTD: not detected within timeout")
        else:
            print(f"MTTD detected: {mttd:.2f}s")
    else:
        mttd = None

    # Wait a bit during injection window
    inj_window = max(3, exp_duration // 3)
    print(f"Injection window: sleeping {inj_window}s")
    time.sleep(inj_window)
    timeout = 30

    # Rollback
    if args.scenario:
        print("Rolling back: compound")
        rb = requests.post(f"{args.controller}/rollback/compound", json=scenario_cfg)
        print("Compound rollback response:", rb.status_code, rb.text[:200])
    else:
        print("Rolling back: start", args.service)
        rb = requests.post(
            f"{args.controller}/rollback/start", json={"services": [args.service]}
        )
        print("Controller rollback response:", rb.status_code, rb.text[:200])

    # MTTR: time until health returns (only for simple service stop)
    if not args.scenario:
        start_rb = time.time()
        mttr = None
        for i in range(timeout):
            if health_ok(
                f"http://localhost:{8000 + (1 if args.service == 'gateway' else (2 if args.service == 'auth' else 3))}"
            ):
                mttr = time.time() - start_rb
                break
            time.sleep(1)

        if mttr is None:
            print("MTTR: not detected within timeout")
        else:
            print(f"MTTR detected: {mttr:.2f}s")
    else:
        mttr = None

    # Measure gateway counter after
    after = read_counter_from_metrics(args.gateway, "gateway_requests_total") or 0.0
    t_after = time.time()
    print("Post gateway_requests_total:", after)

    elapsed = t_after - t_before
    throughput = (after - before) / elapsed if elapsed > 0 else 0.0
    print(f"Observed gateway throughput: {throughput:.2f} req/s over {elapsed:.1f}s")

    loader.stop()
    loader.join(timeout=2)

    print("Experiment summary:")
    print("  service:", args.service)
    print("  MTTD:", mttd)
    print("  MTTR:", mttr)
    print("  gateway_throughput_req_per_s:", f"{throughput:.2f}")


if __name__ == "__main__":
    main()
