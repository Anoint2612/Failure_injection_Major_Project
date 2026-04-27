"""
==========================================================================
 PAPER SCRIPT 2: Resource Exhaustion (CPU Stress) — Case Study
==========================================================================
 Reference: Section 6.2 — "Case study: resource exhaustion and OOM thrashing"
 
 This script runs the secondary experiment from the paper. It injects
 escalating CPU stress (1, 2, 4, 8 workers) into the data-service
 and measures the resulting degradation at the API Gateway.
 
 Outputs:
   - Table 2: CPU Stress metrics across worker counts (CSV + console)
   - Graph 3: Response latency under escalating CPU contention
 
 Prerequisites:
   - Backend running: uvicorn main:app --host 0.0.0.0 --port 5050
   - Target app running: cd target-app && docker compose up -d
   - pip install matplotlib requests numpy (in your venv)
==========================================================================
"""

import requests
import time
import json
import numpy as np
import os

# ─── CONFIG ──────────────────────────────────────────────────────
CONTROLLER = "http://localhost:5050"
GATEWAY_URL = "http://localhost:8000/dashboard"
TARGET_SERVICE = "data-service"

# CPU worker counts to test — escalating resource contention
CPU_WORKERS = [1, 2, 4]
STRESS_TIMEOUT = 30      # Duration of stress injection in seconds
REQUESTS_PER_PHASE = 5
ITERATIONS = 2           # Fewer iterations since stress tests are slower
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── HELPER ──────────────────────────────────────────────────────
def probe_latency(url, timeout=15):
    try:
        start = time.time()
        r = requests.get(url, timeout=timeout)
        return round(time.time() - start, 4), r.status_code
    except requests.exceptions.Timeout:
        return timeout, "timeout"
    except Exception as e:
        return -1, str(e)

def run_stress_experiment(cpu_workers):
    """Run a 3-phase CPU stress experiment."""
    result = {"cpu_workers": cpu_workers, "baseline": [], "during_fault": [], "post_recovery": []}
    
    # Phase 1: Baseline
    for i in range(REQUESTS_PER_PHASE):
        lat, status = probe_latency(GATEWAY_URL)
        result["baseline"].append({"request": i+1, "latency": lat, "status": status})
    
    # Phase 2: Inject CPU Stress
    t_inject = time.time()
    requests.post(
        f"{CONTROLLER}/inject/cpu_stress/{TARGET_SERVICE}?cpu={cpu_workers}&timeout={STRESS_TIMEOUT}"
    )
    time.sleep(3)  # Allow stress to ramp up
    
    t_detected = None
    baseline_mean = np.mean([r["latency"] for r in result["baseline"]])
    
    for i in range(REQUESTS_PER_PHASE):
        lat, status = probe_latency(GATEWAY_URL)
        result["during_fault"].append({"request": i+1, "latency": lat, "status": status})
        if t_detected is None and lat > baseline_mean * 1.5:
            t_detected = time.time()
    
    detection_time = (t_detected - t_inject) if t_detected else 0
    
    # Phase 3: Wait for stress timeout & measure recovery
    remaining = max(0, STRESS_TIMEOUT - (time.time() - t_inject))
    if remaining > 0:
        print(f"    Waiting {remaining:.0f}s for stress-ng timeout...", end=" ", flush=True)
        time.sleep(remaining + 2)
        print("done.")
    
    t_recover_start = time.time()
    # Also explicitly try to recover
    try:
        requests.post(f"{CONTROLLER}/recover/cpu_stress/{TARGET_SERVICE}", timeout=5)
    except:
        pass
    time.sleep(3)
    
    baseline_std = np.std([r["latency"] for r in result["baseline"]]) if len(result["baseline"]) > 1 else 0.01
    t_stabilized = None
    
    for i in range(REQUESTS_PER_PHASE):
        lat, status = probe_latency(GATEWAY_URL)
        result["post_recovery"].append({"request": i+1, "latency": lat, "status": status})
        if t_stabilized is None and abs(lat - baseline_mean) <= 0.05 * baseline_std + baseline_mean * 0.1:
            t_stabilized = time.time()
    
    if t_stabilized is None:
        t_stabilized = time.time()
    
    recovery_time = t_stabilized - t_recover_start
    
    # Compute metrics
    avg_baseline = np.mean([r["latency"] for r in result["baseline"]])
    avg_during = np.mean([r["latency"] for r in result["during_fault"]])
    avg_recovery = np.mean([r["latency"] for r in result["post_recovery"]])
    
    degradation = abs((avg_baseline - avg_during) / avg_baseline) if avg_baseline > 0 else 0
    
    all_requests = result["baseline"] + result["during_fault"] + result["post_recovery"]
    successful = sum(1 for r in all_requests if r["status"] != "timeout" and r["status"] != -1)
    availability = successful / len(all_requests) if all_requests else 0
    
    result["metrics"] = {
        "mttd": round(detection_time, 3),
        "mttr": round(recovery_time, 3),
        "degradation": round(degradation, 4),
        "availability": round(availability, 4),
        "avg_baseline_s": round(avg_baseline, 4),
        "avg_during_s": round(avg_during, 4),
        "avg_recovery_s": round(avg_recovery, 4),
    }
    return result

# ─── MAIN ────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("  PAPER EXPERIMENT: CPU Stress Resource Exhaustion Case Study")
    print("  Reference: Section 6.2 of Research Paper")
    print("=" * 70)
    
    all_results = []
    
    for workers in CPU_WORKERS:
        print(f"\n{'─'*50}")
        print(f"  Testing: {workers} CPU stress workers on {TARGET_SERVICE}")
        print(f"{'─'*50}")
        
        iteration_metrics = []
        for it in range(ITERATIONS):
            print(f"  Iteration {it+1}/{ITERATIONS}...", flush=True)
            result = run_stress_experiment(workers)
            iteration_metrics.append(result["metrics"])
            print(f"    Deg={result['metrics']['degradation']:.3f}, "
                  f"MTTD={result['metrics']['mttd']:.2f}s, "
                  f"MTTR={result['metrics']['mttr']:.2f}s")
            time.sleep(5)
        
        avg_metrics = {}
        for key in iteration_metrics[0]:
            vals = [m[key] for m in iteration_metrics]
            avg_metrics[key] = round(np.mean(vals), 4)
        avg_metrics["cpu_workers"] = workers
        all_results.append(avg_metrics)
    
    # Print Table 2
    print("\n\n" + "=" * 70)
    print("  TABLE 2: CPU Stress Resource Exhaustion Metrics")
    print("=" * 70)
    header = f"{'Workers':>8} │ {'Avg Base(s)':>11} │ {'Avg Fault(s)':>12} │ {'Avg Recov(s)':>12} │ {'Degrad.':>8} │ {'MTTD(s)':>8} │ {'MTTR(s)':>8} │ {'Avail.':>7}"
    print(header)
    print("─" * len(header))
    for r in all_results:
        print(f"{r['cpu_workers']:>8} │ {r['avg_baseline_s']:>11.4f} │ {r['avg_during_s']:>12.4f} │ {r['avg_recovery_s']:>12.4f} │ {r['degradation']:>8.4f} │ {r['mttd']:>8.3f} │ {r['mttr']:>8.3f} │ {r['availability']:>7.4f}")
    
    # Save data
    data_path = os.path.join(OUTPUT_DIR, "stress_results.json")
    with open(data_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n✅ Raw data saved to: {data_path}")
    
    # Generate Graph 3
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        workers_labels = [str(r["cpu_workers"]) for r in all_results]
        baselines = [r["avg_baseline_s"] for r in all_results]
        durings = [r["avg_during_s"] for r in all_results]
        recoveries = [r["avg_recovery_s"] for r in all_results]
        
        fig, ax = plt.subplots(figsize=(10, 6))
        x = np.arange(len(workers_labels))
        width = 0.25
        
        ax.bar(x - width, baselines, width, label='Baseline', color='#34d399', edgecolor='white', linewidth=0.5)
        ax.bar(x, durings, width, label='During CPU Stress', color='#fbbf24', edgecolor='white', linewidth=0.5)
        ax.bar(x + width, recoveries, width, label='Post Recovery', color='#60a5fa', edgecolor='white', linewidth=0.5)
        
        ax.set_xlabel('CPU Stress Workers', fontsize=12, fontweight='bold')
        ax.set_ylabel('Average Response Latency (seconds)', fontsize=12, fontweight='bold')
        ax.set_title('Figure 3: Response Latency Under Escalating CPU Resource Contention', fontsize=13, fontweight='bold', pad=15)
        ax.set_xticks(x)
        ax.set_xticklabels([f'{w} worker(s)' for w in workers_labels])
        ax.legend(fontsize=10)
        ax.grid(axis='y', alpha=0.3)
        ax.set_facecolor('#f8f9fc')
        fig.tight_layout()
        
        graph3_path = os.path.join(OUTPUT_DIR, "graph3_cpu_stress.png")
        fig.savefig(graph3_path, dpi=200, bbox_inches='tight')
        plt.close(fig)
        print(f"📊 Graph 3 saved to: {graph3_path}")
        
    except ImportError:
        print("⚠️  matplotlib not installed. Run: pip install matplotlib")
    
    print("\n✅ Experiment complete! Use the data for Table 2 and Figure 3 in your paper.")

if __name__ == "__main__":
    main()
