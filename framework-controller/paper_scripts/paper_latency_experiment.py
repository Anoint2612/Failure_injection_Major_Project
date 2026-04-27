"""
==========================================================================
 PAPER SCRIPT 1: Network Latency Injection — Case Study
==========================================================================
 Reference: Section 6.1 — "Case study: severe network latency and thread starvation"
 
 This script runs the primary experiment from the paper. It injects
 increasing network latency (500ms, 1000ms, 2000ms, 3000ms, 5000ms)
 into the auth-service and measures the resulting degradation at the
 API Gateway. For each severity, it runs N iterations and calculates:
   - MTTD (Mean Time To Detection)
   - MTTR (Mean Time To Recovery)
   - Degradation Factor
   - Failure Amplification Factor (FAF)
   - Availability
 
 Outputs:
   - Table 1: Per-severity metrics (CSV + console)
   - Graph 1: Latency across 3 phases (Baseline / During Fault / Recovery)
   - Graph 2: Failure Amplification Factor (FAF) vs Injected Delay
 
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
TARGET_SERVICE = "auth-service"
PROBE_URL = GATEWAY_URL  # We probe the gateway to see cascading impact

# Delay values to test (in ms) — escalating severity as per paper methodology
DELAY_VALUES = [500, 1000, 2000, 3000, 5000]
REQUESTS_PER_PHASE = 5   # Requests per phase (baseline/fault/recovery)
ITERATIONS = 3           # Repeat each delay N times for statistical significance
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── HELPER: Measure latency of a single probe ──────────────────
def probe_latency(url, timeout=15):
    """Send a GET request and return (latency_seconds, status_code)."""
    try:
        start = time.time()
        r = requests.get(url, timeout=timeout)
        return round(time.time() - start, 4), r.status_code
    except requests.exceptions.Timeout:
        return timeout, "timeout"
    except Exception as e:
        return -1, str(e)

# ─── HELPER: Run a single 3-phase experiment ────────────────────
def run_single_experiment(delay_ms):
    """
    Runs one complete 3-phase experiment:
      Phase 1: Baseline (no fault)
      Phase 2: During Fault (latency injected)
      Phase 3: Post Recovery (fault removed)
    Returns dict with raw latencies and computed timings.
    """
    result = {"delay_ms": delay_ms, "baseline": [], "during_fault": [], "post_recovery": []}
    
    # ── PHASE 1: BASELINE ────────────────────────────────────────
    for i in range(REQUESTS_PER_PHASE):
        lat, status = probe_latency(GATEWAY_URL)
        result["baseline"].append({"request": i+1, "latency": lat, "status": status})
    
    # ── PHASE 2: INJECT FAULT & MEASURE ──────────────────────────
    t_inject = time.time()
    requests.post(f"{CONTROLLER}/inject/latency/{TARGET_SERVICE}?delay_ms={delay_ms}")
    
    # Measure detection time: first request that shows elevated latency
    t_detected = None
    for i in range(REQUESTS_PER_PHASE):
        lat, status = probe_latency(GATEWAY_URL)
        result["during_fault"].append({"request": i+1, "latency": lat, "status": status})
        if t_detected is None and lat > np.mean([r["latency"] for r in result["baseline"]]) * 1.5:
            t_detected = time.time()
    
    detection_time = (t_detected - t_inject) if t_detected else 0
    
    # ── PHASE 3: RECOVER & MEASURE ───────────────────────────────
    t_recover_start = time.time()
    requests.post(f"{CONTROLLER}/recover/latency/{TARGET_SERVICE}")
    time.sleep(2)  # Allow network stack to stabilize
    
    baseline_mean = np.mean([r["latency"] for r in result["baseline"]])
    baseline_std = np.std([r["latency"] for r in result["baseline"]]) if len(result["baseline"]) > 1 else 0.01
    t_stabilized = None
    
    for i in range(REQUESTS_PER_PHASE):
        lat, status = probe_latency(GATEWAY_URL)
        result["post_recovery"].append({"request": i+1, "latency": lat, "status": status})
        # Paper formula: stabilization when |P(T_stab) - P_base| <= 0.05σ
        if t_stabilized is None and abs(lat - baseline_mean) <= 0.05 * baseline_std + baseline_mean * 0.1:
            t_stabilized = time.time()
    
    if t_stabilized is None:
        t_stabilized = time.time()
    
    recovery_time = t_stabilized - t_recover_start
    
    # ── COMPUTE PAPER METRICS ────────────────────────────────────
    avg_baseline = np.mean([r["latency"] for r in result["baseline"]])
    avg_during = np.mean([r["latency"] for r in result["during_fault"]])
    avg_recovery = np.mean([r["latency"] for r in result["post_recovery"]])
    
    # Degradation Factor (Section 5)
    degradation = (avg_baseline - avg_during) / avg_baseline if avg_baseline > 0 else 0
    # We use absolute degradation (during is always worse)
    degradation = abs(degradation)
    
    # Failure Amplification Factor (Section 5)
    delta_gateway = avg_during - avg_baseline  # Observed degradation at gateway
    delta_injected = delay_ms / 1000.0         # Injected delay in seconds
    faf = delta_gateway / delta_injected if delta_injected > 0 else 0
    
    # Availability: fraction of non-timeout requests during experiment
    all_requests = result["baseline"] + result["during_fault"] + result["post_recovery"]
    successful = sum(1 for r in all_requests if r["status"] != "timeout" and r["status"] != -1)
    availability = successful / len(all_requests) if all_requests else 0
    
    # Total experiment time for uptime/downtime calculation
    fault_duration = sum(r["latency"] for r in result["during_fault"])
    total_duration = sum(r["latency"] for r in all_requests)
    
    result["metrics"] = {
        "mttd": round(detection_time, 3),
        "mttr": round(recovery_time, 3),
        "degradation": round(degradation, 4),
        "faf": round(faf, 4),
        "availability": round(availability, 4),
        "avg_baseline_s": round(avg_baseline, 4),
        "avg_during_s": round(avg_during, 4),
        "avg_recovery_s": round(avg_recovery, 4),
    }
    return result

# ─── MAIN EXPERIMENT LOOP ───────────────────────────────────────
def main():
    print("=" * 70)
    print("  PAPER EXPERIMENT: Network Latency Injection Case Study")
    print("  Reference: Section 6.1 of Research Paper")
    print("=" * 70)
    
    all_results = []
    
    for delay in DELAY_VALUES:
        print(f"\n{'─'*50}")
        print(f"  Testing: {delay}ms latency injection on {TARGET_SERVICE}")
        print(f"  Iterations: {ITERATIONS}")
        print(f"{'─'*50}")
        
        iteration_metrics = []
        for it in range(ITERATIONS):
            print(f"  Iteration {it+1}/{ITERATIONS}...", end=" ", flush=True)
            result = run_single_experiment(delay)
            iteration_metrics.append(result["metrics"])
            print(f"FAF={result['metrics']['faf']:.3f}, "
                  f"Deg={result['metrics']['degradation']:.3f}, "
                  f"MTTD={result['metrics']['mttd']:.2f}s")
            time.sleep(3)  # Cool-down between iterations
        
        # Average across iterations
        avg_metrics = {}
        for key in iteration_metrics[0]:
            vals = [m[key] for m in iteration_metrics]
            avg_metrics[key] = round(np.mean(vals), 4)
        
        avg_metrics["delay_ms"] = delay
        all_results.append(avg_metrics)
    
    # ─── PRINT TABLE 1 ──────────────────────────────────────────
    print("\n\n" + "=" * 70)
    print("  TABLE 1: Per-Severity Latency Experiment Metrics")
    print("=" * 70)
    header = f"{'Delay(ms)':>10} │ {'Avg Base(s)':>11} │ {'Avg Fault(s)':>12} │ {'Avg Recov(s)':>12} │ {'Degrad.':>8} │ {'FAF':>7} │ {'MTTD(s)':>8} │ {'MTTR(s)':>8} │ {'Avail.':>7}"
    print(header)
    print("─" * len(header))
    for r in all_results:
        print(f"{r['delay_ms']:>10} │ {r['avg_baseline_s']:>11.4f} │ {r['avg_during_s']:>12.4f} │ {r['avg_recovery_s']:>12.4f} │ {r['degradation']:>8.4f} │ {r['faf']:>7.4f} │ {r['mttd']:>8.3f} │ {r['mttr']:>8.3f} │ {r['availability']:>7.4f}")
    
    # ─── SAVE RAW DATA ──────────────────────────────────────────
    data_path = os.path.join(OUTPUT_DIR, "latency_results.json")
    with open(data_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n✅ Raw data saved to: {data_path}")
    
    # ─── GENERATE GRAPHS ────────────────────────────────────────
    try:
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
        import matplotlib.pyplot as plt
        
        delays = [r["delay_ms"] for r in all_results]
        baselines = [r["avg_baseline_s"] for r in all_results]
        durings = [r["avg_during_s"] for r in all_results]
        recoveries = [r["avg_recovery_s"] for r in all_results]
        fafs = [r["faf"] for r in all_results]
        
        # ── GRAPH 1: Phase Latency Comparison ────────────────────
        fig, ax = plt.subplots(figsize=(10, 6))
        x = np.arange(len(delays))
        width = 0.25
        
        bars1 = ax.bar(x - width, baselines, width, label='Baseline', color='#34d399', edgecolor='white', linewidth=0.5)
        bars2 = ax.bar(x, durings, width, label='During Fault', color='#f87171', edgecolor='white', linewidth=0.5)
        bars3 = ax.bar(x + width, recoveries, width, label='Post Recovery', color='#60a5fa', edgecolor='white', linewidth=0.5)
        
        ax.set_xlabel('Injected Latency (ms)', fontsize=12, fontweight='bold')
        ax.set_ylabel('Average Response Latency (seconds)', fontsize=12, fontweight='bold')
        ax.set_title('Figure 1: Three-Phase Latency Comparison Across Fault Severities', fontsize=13, fontweight='bold', pad=15)
        ax.set_xticks(x)
        ax.set_xticklabels([f'{d}ms' for d in delays])
        ax.legend(fontsize=10, loc='upper left')
        ax.grid(axis='y', alpha=0.3)
        ax.set_facecolor('#f8f9fc')
        fig.tight_layout()
        
        graph1_path = os.path.join(OUTPUT_DIR, "graph1_phase_latency.png")
        fig.savefig(graph1_path, dpi=200, bbox_inches='tight')
        plt.close(fig)
        print(f"📊 Graph 1 saved to: {graph1_path}")
        
        # ── GRAPH 2: Failure Amplification Factor ────────────────
        fig2, ax2 = plt.subplots(figsize=(10, 6))
        ax2.plot(delays, fafs, 'o-', color='#6c63ff', linewidth=2.5, markersize=10, markerfacecolor='white', markeredgewidth=2.5)
        ax2.axhline(y=1.0, color='#f87171', linestyle='--', linewidth=1.5, label='FAF = 1.0 (No Amplification)')
        ax2.fill_between(delays, 1.0, fafs, alpha=0.15, color='#6c63ff', label='Resilience Debt Zone')
        
        ax2.set_xlabel('Injected Latency (ms)', fontsize=12, fontweight='bold')
        ax2.set_ylabel('Failure Amplification Factor (FAF)', fontsize=12, fontweight='bold')
        ax2.set_title('Figure 2: Failure Amplification Factor — Non-Linear Fault Propagation', fontsize=13, fontweight='bold', pad=15)
        ax2.legend(fontsize=10)
        ax2.grid(alpha=0.3)
        ax2.set_facecolor('#f8f9fc')
        fig2.tight_layout()
        
        graph2_path = os.path.join(OUTPUT_DIR, "graph2_faf_curve.png")
        fig2.savefig(graph2_path, dpi=200, bbox_inches='tight')
        plt.close(fig2)
        print(f"📊 Graph 2 saved to: {graph2_path}")
        
    except ImportError:
        print("⚠️  matplotlib not installed. Run: pip install matplotlib")
        print("   Graphs were not generated, but raw data is saved in latency_results.json")
    
    print("\n✅ Experiment complete! Use the data for Table 1 and Figures 1-2 in your paper.")

if __name__ == "__main__":
    main()
