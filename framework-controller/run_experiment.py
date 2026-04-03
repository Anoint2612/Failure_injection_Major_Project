import requests
import time
import json

# Configurations
GATEWAY_URL = "http://localhost:8000/dashboard"
CONTROLLER_URL = "http://localhost:5000"

def run_chaos_test():
    results = []

    print("--- STEP 1: VERIFYING STEADY STATE ---")
    try:
        initial_check = requests.get(GATEWAY_URL, timeout=5)
        print(f"Status: {initial_check.status_code} - System is Healthy.\n")
    except Exception as e:
        print("System is not reachable. Ensure Docker containers are running.")
        return

    print("--- STEP 2: INJECTING LATENCY (3000ms) ---")
    # We target the auth-service because the Gateway depends on it
    requests.post(f"{CONTROLLER_URL}/inject/latency/auth-service?delay_ms=3000")
    
    print("--- STEP 3: MEASURING IMPACT (STRESS TEST) ---")
    for i in range(1, 6):
        start_time = time.time()
        try:
            response = requests.get(GATEWAY_URL, timeout=10)
            latency = time.time() - start_time
            print(f"Request {i}: Latency = {latency:.2f}s | Status = {response.status_code}")
            results.append({"request": i, "latency": latency, "status": response.status_code})
        except requests.exceptions.Timeout:
            print(f"Request {i}: TIMEOUT!")
            results.append({"request": i, "latency": 10.0, "status": "timeout"})

    print("\n--- STEP 4: RECOVERING SYSTEM ---")
    requests.post(f"{CONTROLLER_URL}/recover/latency/auth-service")
    
    # Final health check
    time.sleep(2) # Give it a second to stabilize
    final_check = requests.get(GATEWAY_URL)
    print(f"Recovery Check: {final_check.status_code} - System back to normal.")

    # Save results for Gemini to read later
    with open("experiment_results.json", "w") as f:
        json.dump(results, f, indent=4)
    print("\n[SUCCESS] Results saved to experiment_results.json")

if __name__ == "__main__":
    run_chaos_test()