import logging
import os
import docker

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] [agent/%(module)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger(__name__)

class StateInjector:
    def __init__(self):
        try:
            self.client = docker.from_env()
            logger.info("[state] Docker client connected")
        except Exception as e:
            self.client = None
            logger.error(f"[state] Docker unavailable: {e}")

    def _get_container(self, name: str):
        if not self.client:
            return None, "Docker client not available"
        try:
            return self.client.containers.get(name), None
        except docker.errors.NotFound:
            return None, f"Container '{name}' not found"
        except Exception as e:
            return None, str(e)

    def kill_container(self, container_name: str, signal: str = 'SIGKILL'):
        logger.info(f"[state] Killing container: {container_name} (signal={signal})")
        container, err = self._get_container(container_name)
        if err:
            logger.error(f"[state] {err}")
            return False, err
        try:
            container.kill(signal=signal)
            msg = f"Killed container '{container_name}' with {signal}"
            logger.info(f"[state] {msg}")
            return True, msg
        except Exception as e:
            logger.error(f"[state] Kill failed for '{container_name}': {e}")
            return False, str(e)

    def pause_container(self, container_name: str):
        logger.info(f"[state] Pausing container: {container_name}")
        container, err = self._get_container(container_name)
        if err:
            logger.error(f"[state] {err}")
            return False, err
        try:
            container.pause()
            msg = f"Paused container '{container_name}'"
            logger.info(f"[state] {msg}")
            return True, msg
        except Exception as e:
            logger.error(f"[state] Pause failed: {e}")
            return False, str(e)

    def unpause_container(self, container_name: str):
        logger.info(f"[state] Unpausing container: {container_name}")
        container, err = self._get_container(container_name)
        if err:
            logger.error(f"[state] {err}")
            return False, err
        try:
            container.unpause()
            msg = f"Unpaused container '{container_name}'"
            logger.info(f"[state] {msg}")
            return True, msg
        except Exception as e:
            logger.error(f"[state] Unpause failed: {e}")
            return False, str(e)

    def cleanup_paused(self):
        """Unpauses all paused containers — called on ABORT_ALL."""
        if not self.client:
            return
        try:
            for container in self.client.containers.list(filters={"status": "paused"}):
                logger.warning(f"[state] ABORT cleanup: unpausing '{container.name}'")
                container.unpause()
        except Exception as e:
            logger.error(f"[state] Cleanup failed: {e}")
