import time
import threading
import requests
import socket
import os
import logging

from injectors.state import StateInjector
from injectors.network import NetworkInjector
from injectors.resource import ResourceInjector
from discovery import HeuristicDiscovery

# Structured logging — level configurable via LOG_LEVEL env var
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] [agent/%(module)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger(__name__)

CONTROLLER_URL = os.getenv("CONTROLLER_URL", "http://controller:8080/api/v1")

class ChaosAgent:
    def __init__(self):
        self.hostname = socket.gethostname()
        self.ip_address = socket.gethostbyname(self.hostname)
        self.agent_id = None
        self._current_experiment_id = None

        # Initialize injector plugins
        self.state_injector = StateInjector()
        self.network_injector = NetworkInjector()
        self.resource_injector = ResourceInjector()

    def register(self):
        discovery = HeuristicDiscovery()
        live_profile = discovery.discover_environment()

        payload = {
            "hostname": self.hostname,
            "ip_address": self.ip_address,
            "discovery_profile": live_profile
        }
        try:
            res = requests.post(f"{CONTROLLER_URL}/agents/register", json=payload, timeout=10)
            res.raise_for_status()
            data = res.json()
            self.agent_id = data["agent_id"]
            logger.info(f"Registered with orchestrator. Agent ID: {self.agent_id} | Host: {self.hostname}")
        except Exception as e:
            logger.error(f"Registration failed: {e}. Retrying in 5s...")
            time.sleep(5)
            self.register()

    def _report_result(self, experiment_id: str, status: str, message: str):
        """Reports experiment completion/failure back to the controller."""
        if not self.agent_id or not experiment_id:
            return
        try:
            requests.post(
                f"{CONTROLLER_URL}/agents/{self.agent_id}/experiment/result",
                json={"experiment_id": experiment_id, "status": status, "message": message},
                timeout=5
            )
            logger.info(f"Reported result for {experiment_id}: {status} — {message}")
        except Exception as e:
            logger.warning(f"Could not report result to controller: {e}")

    def _run_stress(self, experiment_id: str, cpu_workers: int = 1, timeout_seconds: int = 30):
        """Runs CPU stress in a daemon thread so heartbeat loop stays live."""
        logger.info(f"[stress] Starting {cpu_workers} CPU worker(s) for {timeout_seconds}s")
        success, msg = self.resource_injector.execute_stress(
            cpu_workers=cpu_workers, timeout_seconds=timeout_seconds
        )
        if success:
            logger.info(f"[stress] Completed: {msg}")
        else:
            logger.error(f"[stress] Failed: {msg}")
        self._report_result(experiment_id, "completed" if success else "failed", msg)

    def heartbeat_loop(self):
        while True:
            if not self.agent_id:
                time.sleep(3)
                continue

            try:
                res = requests.post(
                    f"{CONTROLLER_URL}/agents/{self.agent_id}/heartbeat",
                    timeout=10
                )
                if res.status_code == 404:
                    logger.warning("Orchestrator lost agent record. Re-registering...")
                    self.register()
                    continue

                data = res.json()
                action = data.get("action")

                if action == "ABORT_ALL":
                    logger.warning(">>> SAFETY ABORT RECEIVED — halting all injections <<<")
                    ok, msg = self.network_injector.remove_latency()
                    logger.info(f"[abort] Network cleanup: {msg}")
                    # Unpause any paused containers
                    self.state_injector.cleanup_paused()

                elif action == "RUN_EXPERIMENT":
                    exp = data.get("payload", {})
                    experiment_id = exp.get("id", "unknown")
                    logger.info(f"Received experiment: {exp.get('name')} (id={experiment_id})")
                    self._current_experiment_id = experiment_id
                    self.execute_experiment(exp)

                else:
                    logger.debug("Heartbeat: SLEEP (no pending work)")

            except requests.exceptions.ConnectionError:
                logger.warning(f"Orchestrator unreachable at {CONTROLLER_URL}. Will retry...")
            except Exception as e:
                logger.error(f"Heartbeat error: {e}", exc_info=True)

            time.sleep(3)

    def execute_experiment(self, exp_def: dict):
        """
        Dispatches an experiment to the correct injector.
        Handles all capability names sent by the dashboard UI.
        """
        name = exp_def.get("name", "").lower()
        params = exp_def.get("parameters", {})
        target_selector = exp_def.get("target_selector", {})
        experiment_id = exp_def.get("id", "unknown")

        # Resolve target container: dashboard sends both 'container' and 'agent_id'
        target = (
            target_selector.get("container")
            or target_selector.get("name")
            or params.get("container")
        )

        duration = int(params.get("duration_seconds", 30))

        logger.info(f"Executing experiment '{name}' | target='{target}' | duration={duration}s")

        # --- Network Latency ---
        # Matches: "simulate_network_delay", "network-latency", "gateway-auth-latency", etc.
        if "simulate_network_delay" in name or "latency" in name or "network" in name:
            delay = params.get("delay", "200ms")
            success, msg = self.network_injector.inject_latency(delay=delay)
            if success:
                logger.info(f"[network] {msg}")
                # Schedule auto-revert after TTL
                threading.Timer(duration, self._revert_network, args=[experiment_id]).start()
                logger.info(f"[network] Auto-revert scheduled in {duration}s")
            else:
                logger.error(f"[network] Injection failed: {msg}")
            self._report_result(experiment_id, "running" if success else "failed", msg)

        # --- CPU/Memory Stress ---
        # Matches: "spike_cpu_memory", "resource-stress", "cpu-stress", etc.
        elif "spike_cpu_memory" in name or "stress" in name or "cpu" in name or "memory" in name:
            cpu_workers = int(params.get("cpu_workers", 1))
            t = threading.Thread(
                target=self._run_stress,
                args=[experiment_id, cpu_workers, duration],
                daemon=True
            )
            t.start()
            self._report_result(experiment_id, "running", f"Stress started — {cpu_workers} CPU worker(s) for {duration}s")

        # --- Container Crash / Kill ---
        # Matches: "crash_container", "kill-container", "container-crash", etc.
        elif "crash" in name or "kill" in name:
            if not target:
                msg = f"No target container specified for crash experiment '{name}'. Check target_selector."
                logger.error(msg)
                self._report_result(experiment_id, "failed", msg)
                return
            success, msg = self.state_injector.kill_container(target)
            if success:
                logger.info(f"[state] {msg}")
            else:
                logger.error(f"[state] Kill failed: {msg}")
            self._report_result(experiment_id, "completed" if success else "failed", msg)

        else:
            msg = f"Unknown experiment type '{name}'. No injector matched."
            logger.warning(msg)
            self._report_result(experiment_id, "failed", msg)

    def _revert_network(self, experiment_id: str):
        """Called by TTL timer to auto-clean network injection."""
        logger.info(f"[network] TTL expired — reverting latency injection (exp={experiment_id})")
        success, msg = self.network_injector.remove_latency()
        status = "completed" if success else "failed"
        logger.info(f"[network] Revert: {msg}")
        self._report_result(experiment_id, status, f"Auto-reverted: {msg}")


if __name__ == "__main__":
    agent = ChaosAgent()
    agent.register()
    agent.heartbeat_loop()
