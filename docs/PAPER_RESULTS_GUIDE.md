# Research Paper — Results Generation Guide

This guide explains how to execute the experimental scripts to generate the **tables, graphs, and numerical data** required for the research paper:

> **"Controlled Failure Injection Framework for Empirical Resilience Evaluation in Distributed Systems"**

---

## Overview of What Gets Generated

| Output | Paper Reference | Script |
|--------|----------------|--------|
| **Table 1**: Per-severity latency metrics (Baseline / Fault / Recovery) | Section 6.1 | `paper_latency_experiment.py` |
| **Table 2**: CPU stress metrics across worker counts | Section 6.2 | `paper_stress_experiment.py` |
| **Table 3**: Manual Triage vs LLM-Enhanced Framework comparison | Section 6.1, Table 1 | `paper_resilience_score.py` |
| **Table 4**: Composite Resilience Score per experiment | Section 5 | `paper_resilience_score.py` |
| **Graph 1**: Three-phase latency comparison (bar chart) | Section 6.1 | `paper_latency_experiment.py` |
| **Graph 2**: Failure Amplification Factor (FAF) curve | Section 5 | `paper_latency_experiment.py` |
| **Graph 3**: CPU stress latency under escalating contention | Section 6.2 | `paper_stress_experiment.py` |
| **Graph 4**: Composite Resilience Score breakdown (dual panel) | Section 5 | `paper_resilience_score.py` |

---

## Mathematical Formulas Computed

Every formula from **Section 5** of the paper is directly calculated by these scripts:

### 1. Mean Time To Detection (MTTD)
```
MTTD = (1/N) × Σ (Detection_Time_i)
```
**How computed:** The script timestamps the moment the fault is injected (`t_inject`) and the moment the first probe request shows latency exceeding 1.5× the baseline mean (`t_detected`). MTTD = `t_detected - t_inject`, averaged over N iterations.

### 2. Degradation Factor
```
Degradation = |Perf_before - Perf_during| / Perf_before
```
**How computed:** `Perf_before` is the average latency across all baseline-phase probe requests. `Perf_during` is the average latency across all fault-phase probe requests.

### 3. Availability
```
Availability = Successful_Requests / Total_Requests
```
**How computed:** Any request that does NOT timeout or error is "successful." The ratio across all 3 phases gives the availability.

### 4. Failure Amplification Factor (FAF)
```
FAF = ΔL_gateway / ΔL_injected
```
**How computed:** `ΔL_gateway` = average fault-phase latency minus average baseline latency (the OBSERVED degradation at the API Gateway). `ΔL_injected` = the injected delay in seconds (e.g., 3000ms = 3.0s). FAF > 1.0 indicates the system MAGNIFIES faults — this is the "Resilience Debt" mentioned in the paper.

### 5. Mean Time To Recovery (MTTR)
```
MTTR = (1/N) × Σ (T_stab_i - T_fault_removed_i)
where: |P(T_stab) - P_base| ≤ 0.05σ
```
**How computed:** After the fault is removed, the script continuously probes the gateway. The moment a probe's latency returns within 5% standard deviation of the baseline mean, that timestamp is `T_stab`. MTTR = `T_stab - T_fault_removed`.

### 6. Composite Resilience Score
```
R = w1·(MTTD⁻¹) + w2·(MTTR⁻¹) + w3·(Availability) - w4·(Degradation)
```
**How computed:** Script 3 applies normalized inverse values with weights `w1=0.25, w2=0.30, w3=0.30, w4=0.15` and scales the result to a 0–10 range.

---

## Step-by-Step Execution

### Prerequisites

Ensure the following are running before executing ANY script:

```bash
# Terminal 1: Start the target application
cd target-app
docker compose up -d
cd ..

# Terminal 2: Start the framework backend
cd framework-controller
source venv/bin/activate
pip install matplotlib numpy    # One-time install for graphing
uvicorn main:app --host 0.0.0.0 --port 5050 --reload
```

Verify both are alive:
```bash
curl http://localhost:8000/dashboard    # Should return JSON from gateway
curl http://localhost:5050/status       # Should list all services
```

### Step 1: Run the Latency Experiment (Script 1)

This is the **primary case study** (Section 6.1). It tests 5 delay severities (500ms → 5000ms), each repeated 3 times.

```bash
cd framework-controller/paper_scripts
python3 paper_latency_experiment.py
```

**Expected runtime:** ~5-8 minutes (each of 5 severities × 3 iterations × 3 phases with cooldowns).

**Expected outputs:**
- Console: `TABLE 1` printed with all per-severity metrics
- File: `latency_results.json` (raw data for all experiments)
- File: `graph1_phase_latency.png` (bar chart: Baseline vs Fault vs Recovery)
- File: `graph2_faf_curve.png` (line chart: FAF across delay values)

### Step 2: Run the CPU Stress Experiment (Script 2)

This is the **secondary case study** (Section 6.2). It tests 3 CPU worker levels (1, 2, 4), each repeated 2 times.

```bash
python3 paper_stress_experiment.py
```

**Expected runtime:** ~8-12 minutes (stress tests need time to ramp and cool down).

**Expected outputs:**
- Console: `TABLE 2` printed with CPU stress metrics
- File: `stress_results.json` (raw data)
- File: `graph3_cpu_stress.png` (bar chart: latency under CPU contention)

### Step 3: Compute Resilience Scores (Script 3)

This reads the outputs from Scripts 1 & 2 and computes the Composite Resilience Score.

```bash
python3 paper_resilience_score.py
```

**Expected runtime:** Instant (no network calls; pure computation).

**Expected outputs:**
- Console: `TABLE 3` — Manual Triage vs LLM-Enhanced comparison (matches paper Table 1)
- Console: `TABLE 4` — Per-experiment Composite Resilience Scores
- File: `resilience_scores.json`
- File: `graph4_resilience_score.png` (dual panel: component breakdown + final scores)

---

## How to Include Results in the Paper

### Tables

The console output of each script is formatted to be directly transcribed into LaTeX. For example, **Table 3** output maps directly to the paper's existing Table 1:

```latex
\begin{table*}[ht]
\centering
\caption{Performance comparison of diagnostic workflows under network degradation}
\begin{tabular}{lll}
\hline
\textbf{Diagnostic Metric} & \textbf{Traditional Manual Triage} & \textbf{LLM-Enhanced Framework} \\
\hline
MTTD (Detection)        & 120 seconds       & <VALUE FROM TABLE 3> \\
MTTR (Recovery)         & 45 minutes        & <VALUE FROM TABLE 3> \\
FAF (Amplification)     & 3.5x              & <VALUE FROM TABLE 3> \\
Suggested Optimization  & Manual required   & Auto-generated \\
\hline
\end{tabular}
\end{table*}
```

### Graphs

All `.png` graphs are saved at 200 DPI and are ready for direct insertion into LaTeX:

```latex
\begin{figure}[ht]
\centering
\includegraphics[width=\linewidth]{graph1_phase_latency.png}
\caption{Three-phase latency comparison across fault severities}
\end{figure}
```

Copy the PNG files from `framework-controller/paper_scripts/` to wherever your LaTeX project stores images.

### Interpreting the Results

**What to look for in Graph 1 (Phase Latency):**
- The red bars (During Fault) should be dramatically taller than green bars (Baseline)
- The blue bars (Post Recovery) should return close to baseline height — proving the system self-heals
- If blue bars remain elevated, it indicates **systemic hysteresis** (worth mentioning in the paper)

**What to look for in Graph 2 (FAF Curve):**
- If the curve stays ABOVE the red dashed line (FAF=1.0), the system exhibits **Resilience Debt**
- A steep upward slope indicates **non-linear fault amplification** — the architecture magnifies small faults into large outages
- This directly validates the paper's claim about "cascading entropy"

**What to look for in Graph 3 (CPU Stress):**
- Increasing CPU workers should show progressively worse latency
- This validates the paper's claim about thread starvation and resource exhaustion

**What to look for in Graph 4 (Resilience Score):**
- Green bars (score ≥7) = Resilient
- Yellow bars (score 4-7) = At Risk
- Red bars (score <4) = Fragile
- The component breakdown shows WHICH aspect (detection, recovery, availability) is the weakest

---

## Customization

### Changing Experiment Parameters

Edit the constants at the top of each script:

| Variable | Script 1 | Script 2 | Description |
|----------|----------|----------|-------------|
| `DELAY_VALUES` | `[500, 1000, 2000, 3000, 5000]` | — | Latency severities to test |
| `CPU_WORKERS` | — | `[1, 2, 4]` | CPU stress worker counts |
| `REQUESTS_PER_PHASE` | `5` | `5` | Probes per experiment phase |
| `ITERATIONS` | `3` | `2` | Repetitions per configuration |
| `TARGET_SERVICE` | `auth-service` | `data-service` | Which container to attack |

### Changing Resilience Score Weights

Edit the weights in `paper_resilience_score.py`:

```python
W1 = 0.25   # Detection speed importance
W2 = 0.30   # Recovery speed importance
W3 = 0.30   # Availability importance
W4 = 0.15   # Degradation penalty weight
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ConnectionRefused on port 5050` | Start the backend: `uvicorn main:app --host 0.0.0.0 --port 5050` |
| `ConnectionRefused on port 8000` | Start target app: `cd target-app && docker compose up -d` |
| `ModuleNotFoundError: matplotlib` | Install it: `pip install matplotlib numpy` |
| All latencies show ~0.003s during fault | The target container might lack `iproute2`. Check `docker exec <container> which tc` |
| `Operation not permitted` during inject | Ensure `cap_add: NET_ADMIN` and `privileged: true` in target docker-compose.yml |
| Graphs not generating | The script uses `Agg` backend (headless). Check file permissions in the output directory |
