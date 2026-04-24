from dotenv import load_dotenv
import os
from google import genai
import json

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def analyze_results(data: dict) -> str:
    """Analyze experiment telemetry and return an SRE remediation report."""
    # The Prompt: This is the "Secret Sauce" for your research paper
    prompt = f"""
    You are a Senior Site Reliability Engineer (SRE). 
    I ran a chaos engineering experiment on a microservices system.
    Here is the latency data collected during the failure:
    {json.dumps(data)}

    Please provide:
    1. Root Cause Analysis: What happened to the user experience?
    2. Resilience Score: (0-10) based on the recovery and latency.
    3. Remediation: Suggest 2 specific technical improvements (e.g., timeouts, circuit breakers).
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
            
    # If all models fail, return a structured error document
    return f"""
# Service Unavailable
The AI analysis failed after attempting multiple models ({', '.join(models_to_try)}). 
**Error Details:** `{last_exception}`

Please check your GEMINI_API_KEY rate limits or try again later.
"""

if __name__ == "__main__":
    if not os.path.exists("experiment_results.json"):
        print("Error: No 'experiment_results.json' found. Please run an experiment first using 'python run_experiment.py'!")
        exit(1)
        
    with open("experiment_results.json", "r") as f:
        data = json.load(f)
        
    print("🤖 AI Analyst is reviewing your telemetry. Please wait...")
    report = analyze_results(data)
    
    # Save the markdown report to disk
    with open("ai_remediation_report.md", "w") as f:
        f.write(report)
        
    print("\n--- GEMINI AI REMEDIATION REPORT ---")
    print(report)
    print("\n✅ Report successfully saved to 'ai_remediation_report.md'")