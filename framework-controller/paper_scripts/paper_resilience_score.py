"""
==========================================================================
 PAPER SCRIPT 3: Composite Resilience Score & Summary Tables
==========================================================================
 Reference: Section 5 — "Mathematical Modeling of Resilience"
 
 This script reads the JSON outputs from Scripts 1 & 2, then computes:
   - Composite Resilience Score: R = w1*(MTTD^-1) + w2*(MTTR^-1) + w3*Avail - w4*Degrad
   - Table 3: Side-by-side comparison of manual vs LLM-enhanced (matching paper Table 1)
   - Graph 4: Composite Resilience Score Breakdown (stacked bar chart)
 
 Prerequisites:
   - Run paper_latency_experiment.py and paper_stress_experiment.py FIRST
   - Their output JSON files must exist in this directory
   - pip install matplotlib numpy (in your venv)
==========================================================================
"""

import json
import numpy as np
import os

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── Composite Resilience Score Weights (Paper Section 5) ────────
W1 = 0.25   # Weight for MTTD^-1 (detection speed)
W2 = 0.30   # Weight for MTTR^-1 (recovery speed)
W3 = 0.30   # Weight for Availability
W4 = 0.15   # Weight for Degradation (penalty)

def compute_resilience_score(mttd, mttr, availability, degradation):
    """
    Composite Resilience Score from Paper Section 5:
    R = w1*(MTTD^-1) + w2*(MTTR^-1) + w3*(Availability) - w4*(Degradation)
    
    We normalize MTTD^-1 and MTTR^-1 to [0,1] scale for the final score.
    """
    # Prevent division by zero
    mttd_inv = 1.0 / max(mttd, 0.001)
    mttr_inv = 1.0 / max(mttr, 0.001)
    
    # Normalize inverses: cap at reasonable max (e.g., detecting in 0.1s = 10)
    mttd_norm = min(mttd_inv / 10.0, 1.0)
    mttr_norm = min(mttr_inv / 10.0, 1.0)
    
    raw = W1 * mttd_norm + W2 * mttr_norm + W3 * availability - W4 * degradation
    # Scale to 0-10
    score = round(max(0, min(10, raw * 10)), 2)
    return score, {
        "mttd_component": round(W1 * mttd_norm * 10, 2),
        "mttr_component": round(W2 * mttr_norm * 10, 2),
        "availability_component": round(W3 * availability * 10, 2),
        "degradation_penalty": round(W4 * degradation * 10, 2),
    }

def main():
    print("=" * 70)
    print("  PAPER ANALYSIS: Composite Resilience Score & Summary")
    print("  Reference: Section 5 — Mathematical Modeling of Resilience")
    print("=" * 70)
    
    # ─── LOAD DATA ───────────────────────────────────────────────
    latency_path = os.path.join(OUTPUT_DIR, "latency_results.json")
    stress_path = os.path.join(OUTPUT_DIR, "stress_results.json")
    
    latency_data = []
    stress_data = []
    
    if os.path.exists(latency_path):
        with open(latency_path, "r") as f:
            latency_data = json.load(f)
        print(f"✅ Loaded latency results: {len(latency_data)} severity levels")
    else:
        print(f"⚠️  {latency_path} not found. Run paper_latency_experiment.py first!")
    
    if os.path.exists(stress_path):
        with open(stress_path, "r") as f:
            stress_data = json.load(f)
        print(f"✅ Loaded stress results: {len(stress_data)} worker levels")
    else:
        print(f"⚠️  {stress_path} not found. Run paper_stress_experiment.py first!")
    
    if not latency_data and not stress_data:
        print("\n❌ No data available. Run experiment scripts first!")
        return
    
    # ─── TABLE 3: Paper-Style Comparison (Manual vs LLM-Enhanced) ─
    print("\n\n" + "=" * 70)
    print("  TABLE 3: Performance Comparison — Traditional vs LLM-Enhanced")
    print("  (Matches Paper Table 1 format)")
    print("=" * 70)
    
    # Use the 500ms latency experiment for the direct comparison
    # (matching paper's primary case study)
    if latency_data:
        primary = latency_data[0]  # First severity level
        
        # Simulated manual triage values (from paper Section 6.1)
        manual_mttd = 120.0    # Paper states "MTTD of 120 seconds"
        manual_mttr = 45 * 60  # Paper states "45 minutes" = 2700s
        
        framework_mttd = primary["mttd"]
        framework_mttr = primary["mttr"]
        
        mttd_improvement = round((1 - framework_mttd / manual_mttd) * 100, 1)
        mttr_improvement = round((1 - framework_mttr / manual_mttr) * 100, 1)
        
        print(f"\n{'Diagnostic Metric':<35} │ {'Manual Triage':>18} │ {'LLM Framework':>18} │ {'Improvement':>12}")
        print("─" * 90)
        print(f"{'MTTD (Detection)':<35} │ {manual_mttd:>15.1f}s │ {framework_mttd:>15.3f}s │ {mttd_improvement:>10.1f}%")
        print(f"{'MTTR (Recovery)':<35} │ {manual_mttr:>15.1f}s │ {framework_mttr:>15.3f}s │ {mttr_improvement:>10.1f}%")
        print(f"{'FAF (Amplification)':<35} │ {'3.5x (est.)':>18} │ {primary['faf']:>15.3f}x │ {'Identified':>12}")
        print(f"{'Availability':<35} │ {'~0.95 (est.)':>18} │ {primary['availability']:>18.4f} │ {'—':>12}")
        print(f"{'Suggested Fix':<35} │ {'Manual required':>18} │ {'Auto-generated':>18} │ {'—':>12}")
    
    # ─── COMPUTE RESILIENCE SCORES ───────────────────────────────
    print("\n\n" + "=" * 70)
    print("  TABLE 4: Composite Resilience Score per Experiment")
    print("  Formula: R = w1·MTTD⁻¹ + w2·MTTR⁻¹ + w3·Availability - w4·Degradation")
    print(f"  Weights: w1={W1}, w2={W2}, w3={W3}, w4={W4}")
    print("=" * 70)
    
    all_scores = []
    
    header = f"{'Experiment':<25} │ {'MTTD⁻¹':>8} │ {'MTTR⁻¹':>8} │ {'Avail':>8} │ {'Degrad':>8} │ {'Score':>8}"
    print(header)
    print("─" * len(header))
    
    for r in latency_data:
        score, components = compute_resilience_score(
            r["mttd"], r["mttr"], r["availability"], r["degradation"]
        )
        label = f"Latency {r['delay_ms']}ms"
        print(f"{label:<25} │ {components['mttd_component']:>8.2f} │ {components['mttr_component']:>8.2f} │ {components['availability_component']:>8.2f} │ {components['degradation_penalty']:>8.2f} │ {score:>8.2f}")
        all_scores.append({"label": label, "score": score, **components})
    
    for r in stress_data:
        score, components = compute_resilience_score(
            r["mttd"], r["mttr"], r["availability"], r["degradation"]
        )
        label = f"CPU {r['cpu_workers']} worker(s)"
        print(f"{label:<25} │ {components['mttd_component']:>8.2f} │ {components['mttr_component']:>8.2f} │ {components['availability_component']:>8.2f} │ {components['degradation_penalty']:>8.2f} │ {score:>8.2f}")
        all_scores.append({"label": label, "score": score, **components})
    
    # Save scores
    scores_path = os.path.join(OUTPUT_DIR, "resilience_scores.json")
    with open(scores_path, "w") as f:
        json.dump(all_scores, f, indent=2)
    print(f"\n✅ Scores saved to: {scores_path}")
    
    # ─── GRAPH 4: Resilience Score Breakdown ─────────────────────
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        labels = [s["label"] for s in all_scores]
        mttd_comp = [s["mttd_component"] for s in all_scores]
        mttr_comp = [s["mttr_component"] for s in all_scores]
        avail_comp = [s["availability_component"] for s in all_scores]
        degrad_comp = [s["degradation_penalty"] for s in all_scores]
        total_scores = [s["score"] for s in all_scores]
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7), gridspec_kw={'width_ratios': [3, 2]})
        
        # Left: Stacked bar chart of score components
        x = np.arange(len(labels))
        ax1.bar(x, mttd_comp, 0.6, label=f'MTTD⁻¹ (w={W1})', color='#34d399')
        ax1.bar(x, mttr_comp, 0.6, bottom=mttd_comp, label=f'MTTR⁻¹ (w={W2})', color='#60a5fa')
        ax1.bar(x, avail_comp, 0.6, 
                bottom=[m+t for m,t in zip(mttd_comp, mttr_comp)], 
                label=f'Availability (w={W3})', color='#6c63ff')
        ax1.bar(x, [-d for d in degrad_comp], 0.6,
                bottom=[m+t+a for m,t,a in zip(mttd_comp, mttr_comp, avail_comp)],
                label=f'Degradation Penalty (w={W4})', color='#f87171')
        
        ax1.set_xlabel('Experiment', fontsize=11, fontweight='bold')
        ax1.set_ylabel('Score Component', fontsize=11, fontweight='bold')
        ax1.set_title('Figure 4a: Resilience Score Component Breakdown', fontsize=12, fontweight='bold', pad=12)
        ax1.set_xticks(x)
        ax1.set_xticklabels(labels, rotation=30, ha='right', fontsize=9)
        ax1.legend(fontsize=9, loc='upper right')
        ax1.grid(axis='y', alpha=0.3)
        ax1.set_facecolor('#f8f9fc')
        
        # Right: Final score bar chart
        colors = ['#34d399' if s >= 7 else '#fbbf24' if s >= 4 else '#f87171' for s in total_scores]
        bars = ax2.barh(labels, total_scores, color=colors, edgecolor='white', linewidth=0.5)
        ax2.set_xlabel('Composite Resilience Score (0-10)', fontsize=11, fontweight='bold')
        ax2.set_title('Figure 4b: Final Resilience Scores', fontsize=12, fontweight='bold', pad=12)
        ax2.set_xlim(0, 10)
        ax2.axvline(x=7, color='#34d399', linestyle='--', linewidth=1, alpha=0.5, label='Resilient (≥7)')
        ax2.axvline(x=4, color='#fbbf24', linestyle='--', linewidth=1, alpha=0.5, label='At Risk (≥4)')
        ax2.legend(fontsize=9)
        ax2.grid(axis='x', alpha=0.3)
        ax2.set_facecolor('#f8f9fc')
        
        for bar, score in zip(bars, total_scores):
            ax2.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height()/2,
                     f'{score:.1f}', va='center', fontweight='bold', fontsize=10)
        
        fig.tight_layout()
        graph4_path = os.path.join(OUTPUT_DIR, "graph4_resilience_score.png")
        fig.savefig(graph4_path, dpi=200, bbox_inches='tight')
        plt.close(fig)
        print(f"📊 Graph 4 saved to: {graph4_path}")
        
    except ImportError:
        print("⚠️  matplotlib not installed. Run: pip install matplotlib")
    
    print("\n✅ Analysis complete! Use Tables 3-4 and Figure 4 in your paper.")

if __name__ == "__main__":
    main()
