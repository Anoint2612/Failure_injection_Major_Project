import logging
import os
import requests

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] [controller/%(module)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger(__name__)

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")

class SafetyEngine:
    def __init__(self):
        self.error_rate_threshold = float(os.getenv("SAFETY_ERROR_THRESHOLD", "0.05"))  # 5%
        self.mttr_threshold_ms = int(os.getenv("SAFETY_MTTR_MS", "500"))

    def check_health(self) -> bool:
        """
        Queries Prometheus for live error rates.
        Returns False (trigger ABORT_ALL) if 503 error rate exceeds threshold.
        Fails open (returns True) when Prometheus is unreachable so that
        connectivity issues don't block all experiments.
        """
        try:
            query = 'rate(gateway_requests_total{status="503"}[1m])'
            resp = requests.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": query},
                timeout=2
            )
            resp.raise_for_status()
            data = resp.json().get("data", {}).get("result", [])

            if data:
                rate = float(data[0]["value"][1])
                if rate > self.error_rate_threshold:
                    logger.warning(
                        f"SAFETY: 503 error rate {rate:.4f} exceeds threshold {self.error_rate_threshold}. "
                        "Issuing ABORT_ALL."
                    )
                    return False
                logger.debug(f"Safety check passed: 503 rate={rate:.4f} (threshold={self.error_rate_threshold})")
            else:
                logger.debug("Safety check: no data from Prometheus yet — treating as healthy")

        except requests.exceptions.Timeout:
            logger.warning("Safety check: Prometheus timed out — failing open (experiments allowed)")
        except requests.exceptions.ConnectionError:
            logger.warning("Safety check: Prometheus unreachable — failing open (experiments allowed)")
        except Exception as e:
            logger.error(f"Safety check error: {e} — failing open")

        return True

    def issue_abort(self):
        logger.critical("BLAST RADIUS EXCEEDED — broadcasting ABORT_ALL to all polling agents.")
