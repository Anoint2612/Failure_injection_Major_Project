from dotenv import load_dotenv
import os
from google import genai
import json

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def generate_chaos_scenario(architecture: str = None) -> str:
    """Generate an AI-powered chaos scenario based on the system architecture.
    
    Args:
        architecture: Docker Compose YAML string. If None, reads from disk.
    
    Returns:
        Markdown-formatted chaos scenario suggestion with exact parameters.
    """
    if architecture is None:
        with open("../target-app/docker-compose.yml", "r") as f:
            architecture = f.read()

    prompt = f"""
You are a Senior Chaos Engineer and Site Reliability Expert. I have a microservices system described by the following Docker Compose architecture:

```yaml
{architecture}
```

My ChaosController platform supports these exact fault types with these exact configurable parameters:

1. **latency** — Inject network delay via `tc netem`
   - `delay_ms` (100–10000ms, step 100) — default: 2000
   - `jitter_ms` (0–2000ms, step 50) — default: 0

2. **packet_loss** — Drop network packets via `tc netem`
   - `percent` (1–100%) — default: 30
   - `correlation` (0–100%) — default: 25

3. **bandwidth_throttle** — Limit bandwidth via `tc tbf`
   - `rate_kbit` (10–10000 kbit/s) — default: 100

4. **network_partition** — Block traffic to a specific target via `iptables DROP`
   - `target_service` (text) — the service to block communication with

5. **dns_failure** — Break DNS resolution by corrupting `/etc/resolv.conf`
   - No parameters

6. **cpu_stress** — Exhaust CPU via `stress-ng`
   - `cpu` workers (1–8) — default: 1
   - `timeout` seconds (10–300) — default: 30

7. **memory_stress** — Exhaust memory via `stress-ng`
   - `vm_workers` (1–4) — default: 1
   - `vm_bytes` (64M, 128M, 256M, 512M, 1G) — default: 128M
   - `timeout` seconds (10–300) — default: 30

8. **crash** — Hard-stop the container entirely (Docker SDK)
   - No parameters

Please analyze the architecture and provide a **comprehensive chaos testing battle plan** in this exact format:

## 🏗️ Architecture Analysis
- Map out which services depend on which (e.g., "api-gateway calls auth-service and data-service")
- Identify the single points of failure and critical dependency chains

## 🎯 Recommended Test Plan

For each test, provide:
- **Target Service**: (the exact Docker Compose service name to inject the fault on)
- **Fault Type**: (one of the 8 types above)
- **Exact Parameters**: (specific numeric values to use — not defaults, choose values that will cause observable but non-destructive impact)
- **Probe URL**: What endpoint to monitor during this test
- **Hypothesis**: What you predict will happen to the rest of the system
- **What to Watch For**: Specific latency thresholds or error codes that indicate failure

Suggest at least 3 individual tests ranked by severity (start mild, escalate), and then suggest 1 combined multi-fault scenario where 2+ faults are injected simultaneously to simulate a catastrophic event.

## 🔬 Expected Resilience Score
Based on the architecture, predict the system's resilience score (0-10) and explain what architectural improvements would raise it.

Keep your response concise but actionable. Every value you suggest should be directly paste-able into the ChaosController UI.
"""

    models_to_try = [
        "gemini-2.5-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash"
    ]

    last_exception = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            return response.text
        except Exception as e:
            last_exception = e
            print(f"Model {model_name} failed: {e}. Trying fallback...")
            continue

    return f"""
# Service Unavailable
The scenario generation failed after attempting multiple models ({', '.join(models_to_try)}).
**Error Details:** `{last_exception}`

Please check your GEMINI_API_KEY rate limits or try again later.
"""

if __name__ == "__main__":
    print("\n--- AI-GENERATED CHAOS SCENARIO ---")
    report = generate_chaos_scenario()
    print(report)
    
    with open("scenario_generation_report.md", "w") as f:
        f.write(report)
    print("\n✅ Scenario saved to 'scenario_generation_report.md'")