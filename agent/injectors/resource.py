import subprocess
import logging
import os

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] [agent/%(module)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger(__name__)

class ResourceInjector:
    def execute_stress(self, cpu_workers: int = 1, timeout_seconds: int = 30):
        """
        Runs stress-ng. This call BLOCKS for timeout_seconds — caller must run it
        in a daemon thread to keep the heartbeat loop responsive.
        """
        cmd = f"stress-ng --cpu {cpu_workers} --timeout {timeout_seconds}s --metrics-brief"
        logger.info(f"Starting CPU stress: {cmd}")
        try:
            result = subprocess.run(cmd.split(), check=True, capture_output=True, text=True, timeout=timeout_seconds + 5)
            msg = f"Stressed {cpu_workers} CPU(s) for {timeout_seconds}s"
            logger.info(f"[stress-ng] Completed: {msg}")
            if result.stdout:
                logger.debug(f"[stress-ng] stdout: {result.stdout.strip()}")
            return True, msg
        except subprocess.TimeoutExpired:
            msg = f"stress-ng timed out after {timeout_seconds + 5}s"
            logger.error(f"[stress-ng] {msg}")
            return False, msg
        except subprocess.CalledProcessError as e:
            msg = f"stress-ng failed: {e.stderr.strip() if e.stderr else str(e)}"
            logger.error(f"[stress-ng] {msg}")
            return False, msg
        except FileNotFoundError:
            msg = "stress-ng not found. Install with: apt-get install stress-ng"
            logger.error(f"[stress-ng] {msg}")
            return False, msg
