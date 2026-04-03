import subprocess
import logging
import os

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] [agent/%(module)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger(__name__)

class NetworkInjector:
    def inject_latency(self, interface: str = 'eth0', delay: str = '200ms'):
        cmd = f"tc qdisc add dev {interface} root netem delay {delay}"
        logger.info(f"Injecting network latency: {cmd}")
        try:
            result = subprocess.run(cmd.split(), check=True, capture_output=True, text=True)
            msg = f"Injected {delay} latency on {interface}"
            logger.info(f"[tc] Success: {msg}")
            return True, msg
        except subprocess.CalledProcessError as e:
            # tc returns error if qdisc already exists — try replacing instead
            replace_cmd = f"tc qdisc replace dev {interface} root netem delay {delay}"
            logger.warning(f"[tc] add failed ({e.stderr.strip()}), retrying with replace: {replace_cmd}")
            try:
                subprocess.run(replace_cmd.split(), check=True, capture_output=True, text=True)
                msg = f"Replaced qdisc with {delay} latency on {interface}"
                logger.info(f"[tc] Replace success: {msg}")
                return True, msg
            except subprocess.CalledProcessError as e2:
                msg = f"tc failed: {e2.stderr.strip()}"
                logger.error(f"[tc] {msg}")
                return False, msg

    def remove_latency(self, interface: str = 'eth0'):
        cmd = f"tc qdisc del dev {interface} root"
        logger.info(f"Removing network constraints: {cmd}")
        try:
            subprocess.run(cmd.split(), check=True, capture_output=True, text=True)
            msg = f"Removed all network constraints on {interface}"
            logger.info(f"[tc] {msg}")
            return True, msg
        except subprocess.CalledProcessError as e:
            msg = f"tc del failed (may already be clean): {e.stderr.strip()}"
            logger.warning(f"[tc] {msg}")
            return False, msg
