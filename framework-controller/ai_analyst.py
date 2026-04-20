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