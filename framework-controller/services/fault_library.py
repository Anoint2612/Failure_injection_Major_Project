"""
Fault Library — Pluggable fault injection registry.

Each fault is a class with inject() and recover() methods plus metadata
for the frontend to render controls dynamically. Adding a new fault type
means adding a single class — no router or endpoint changes needed.
"""

from abc import ABC, abstractmethod
from typing import Any


class FaultBase(ABC):
    """Base class for all fault types."""

    name: str = ""
    description: str = ""
    category: str = ""  # "network", "resource", "infrastructure"
    parameters: list = []  # Parameter definitions for the frontend

    @abstractmethod
    def inject(self, container, **params) -> dict:
        """Inject the fault into the container. Returns action description."""
        ...

    @abstractmethod
    def recover(self, container, **params) -> dict:
        """Recover from the fault. Returns action description."""
        ...

    def to_dict(self):
        """Serialize fault metadata for the GET /faults API."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "parameters": self.parameters,
        }


# ═══════════════════════════════════════════════════════════
#  INFRASTRUCTURE FAULTS
# ═══════════════════════════════════════════════════════════

class CrashFault(FaultBase):
    name = "crash"
    description = "Simulate a hard crash by stopping the container entirely"
    category = "infrastructure"
    parameters = []

    def inject(self, container, **params):
        container.stop()
        return {"action": f"Stopped container {container.name}"}

    def recover(self, container, **params):
        container.start()
        return {"action": f"Started container {container.name}"}



# ═══════════════════════════════════════════════════════════
#  NETWORK FAULTS
# ═══════════════════════════════════════════════════════════

class LatencyFault(FaultBase):
    name = "latency"
    description = "Inject artificial network delay using tc netem"
    category = "network"
    parameters = [
        {"name": "delay_ms", "type": "range", "default": 2000,
         "min": 100, "max": 10000, "step": 100,
         "description": "Delay in milliseconds"},
        {"name": "jitter_ms", "type": "range", "default": 0,
         "min": 0, "max": 2000, "step": 50,
         "description": "Jitter (variation) in milliseconds"},
    ]

    def inject(self, container, delay_ms=2000, jitter_ms=0, **params):
        jitter_part = f" {jitter_ms}ms" if int(jitter_ms) > 0 else ""
        # Delete any existing rules first, then add fresh
        container.exec_run("tc qdisc del dev eth0 root")
        cmd = f"tc qdisc add dev eth0 root netem delay {delay_ms}ms{jitter_part}"
        container.exec_run(cmd)
        return {"action": f"Added {delay_ms}ms delay (jitter: {jitter_ms}ms) to {container.name}"}

    def recover(self, container, **params):
        container.exec_run("tc qdisc del dev eth0 root")
        return {"action": f"Removed network rules from {container.name}"}


class PacketLossFault(FaultBase):
    name = "packet_loss"
    description = "Drop a percentage of network packets using tc netem"
    category = "network"
    parameters = [
        {"name": "percent", "type": "range", "default": 30,
         "min": 1, "max": 100, "step": 1,
         "description": "Percentage of packets to drop"},
        {"name": "correlation", "type": "range", "default": 25,
         "min": 0, "max": 100, "step": 5,
         "description": "Correlation with previous packet (burst loss)"},
    ]

    def inject(self, container, percent=30, correlation=25, **params):
        container.exec_run("tc qdisc del dev eth0 root")
        cmd = f"tc qdisc add dev eth0 root netem loss {percent}% {correlation}%"
        container.exec_run(cmd)
        return {"action": f"Dropping {percent}% packets (corr: {correlation}%) on {container.name}"}

    def recover(self, container, **params):
        container.exec_run("tc qdisc del dev eth0 root")
        return {"action": f"Removed packet loss from {container.name}"}


class BandwidthThrottleFault(FaultBase):
    name = "bandwidth_throttle"
    description = "Limit outbound bandwidth using tc token bucket filter"
    category = "network"
    parameters = [
        {"name": "rate_kbit", "type": "range", "default": 100,
         "min": 10, "max": 10000, "step": 10,
         "description": "Bandwidth limit in kbit/s"},
    ]

    def inject(self, container, rate_kbit=100, **params):
        container.exec_run("tc qdisc del dev eth0 root")
        burst = max(int(int(rate_kbit) / 10), 1)
        cmd = f"tc qdisc add dev eth0 root tbf rate {rate_kbit}kbit burst {burst}kbit latency 50ms"
        container.exec_run(cmd)
        return {"action": f"Throttled bandwidth to {rate_kbit}kbit/s on {container.name}"}

    def recover(self, container, **params):
        container.exec_run("tc qdisc del dev eth0 root")
        return {"action": f"Removed bandwidth limit from {container.name}"}


class NetworkPartitionFault(FaultBase):
    name = "network_partition"
    description = "Isolate this container from a specific target using iptables DROP"
    category = "network"
    parameters = [
        {"name": "target_service", "type": "text", "default": "",
         "description": "Target service name to block traffic to/from"},
    ]

    def inject(self, container, target_service="", **params):
        if not target_service:
            return {"action": "No target_service specified"}
        # Block both inbound and outbound to the target hostname
        container.exec_run(f"iptables -A OUTPUT -d {target_service} -j DROP")
        container.exec_run(f"iptables -A INPUT -s {target_service} -j DROP")
        return {"action": f"Partitioned {container.name} from {target_service}"}

    def recover(self, container, **params):
        container.exec_run("iptables -F")
        return {"action": f"Flushed all iptables rules on {container.name}"}


class DnsFailureFault(FaultBase):
    name = "dns_failure"
    description = "Break DNS resolution by replacing /etc/resolv.conf"
    category = "network"
    parameters = []

    def inject(self, container, **params):
        # Backup original and replace with a black-hole nameserver
        container.exec_run("cp /etc/resolv.conf /etc/resolv.conf.bak")
        container.exec_run("sh -c 'echo nameserver 127.0.0.1 > /etc/resolv.conf'")
        return {"action": f"DNS resolution disabled on {container.name}"}

    def recover(self, container, **params):
        container.exec_run("cp /etc/resolv.conf.bak /etc/resolv.conf")
        return {"action": f"DNS resolution restored on {container.name}"}


# ═══════════════════════════════════════════════════════════
#  RESOURCE FAULTS
# ═══════════════════════════════════════════════════════════

class CpuStressFault(FaultBase):
    name = "cpu_stress"
    description = "Exhaust CPU using stress-ng workers"
    category = "resource"
    parameters = [
        {"name": "cpu", "type": "range", "default": 1,
         "min": 1, "max": 8, "step": 1,
         "description": "Number of CPU worker threads"},
        {"name": "timeout", "type": "range", "default": 30,
         "min": 10, "max": 300, "step": 10,
         "description": "Duration in seconds"},
    ]

    def inject(self, container, cpu=1, timeout=30, **params):
        cmd = f"stress-ng --cpu {cpu} --timeout {timeout}s"
        container.exec_run(cmd, detach=True)
        return {"action": f"Injected CPU stress ({cpu} workers, {timeout}s) on {container.name}"}

    def recover(self, container, **params):
        container.exec_run("pkill stress-ng")
        return {"action": f"Killed stress-ng on {container.name}"}


class MemoryStressFault(FaultBase):
    name = "memory_stress"
    description = "Exhaust memory using stress-ng VM workers"
    category = "resource"
    parameters = [
        {"name": "vm_workers", "type": "range", "default": 1,
         "min": 1, "max": 4, "step": 1,
         "description": "Number of VM worker threads"},
        {"name": "vm_bytes", "type": "select", "default": "128M",
         "options": ["64M", "128M", "256M", "512M", "1G"],
         "description": "Memory to consume per worker"},
        {"name": "timeout", "type": "range", "default": 30,
         "min": 10, "max": 300, "step": 10,
         "description": "Duration in seconds"},
    ]

    def inject(self, container, vm_workers=1, vm_bytes="128M", timeout=30, **params):
        cmd = f"stress-ng --vm {vm_workers} --vm-bytes {vm_bytes} --timeout {timeout}s"
        container.exec_run(cmd, detach=True)
        return {"action": f"Memory stress ({vm_workers}x{vm_bytes}, {timeout}s) on {container.name}"}

    def recover(self, container, **params):
        container.exec_run("pkill stress-ng")
        return {"action": f"Killed stress-ng on {container.name}"}


class DiskIoStressFault(FaultBase):
    name = "disk_io_stress"
    description = "Generate heavy disk I/O using stress-ng HDD workers"
    category = "resource"
    parameters = [
        {"name": "hdd_workers", "type": "range", "default": 1,
         "min": 1, "max": 4, "step": 1,
         "description": "Number of HDD worker threads"},
        {"name": "timeout", "type": "range", "default": 30,
         "min": 10, "max": 300, "step": 10,
         "description": "Duration in seconds"},
    ]

    def inject(self, container, hdd_workers=1, timeout=30, **params):
        cmd = f"stress-ng --hdd {hdd_workers} --timeout {timeout}s"
        container.exec_run(cmd, detach=True)
        return {"action": f"Disk I/O stress ({hdd_workers} workers, {timeout}s) on {container.name}"}

    def recover(self, container, **params):
        container.exec_run("pkill stress-ng")
        return {"action": f"Killed stress-ng on {container.name}"}


# ═══════════════════════════════════════════════════════════
#  APPLICATION & SYSTEM FAULTS
# ═══════════════════════════════════════════════════════════

class ClockSkewFault(FaultBase):
    name = "clock_skew"
    description = "Manipulate container system clock to simulate time drift"
    category = "system"
    parameters = [
        {"name": "offset_seconds", "type": "range", "default": 300, "min": -86400, "max": 86400, "step": 60,
         "description": "Seconds to shift the clock forward (positive) or backward (negative)"},
    ]

    def inject(self, container, offset_seconds=300, **params):
        offset = int(offset_seconds)
        sign = "-" if offset < 0 else "+"
        secs = abs(offset)
        # Note: changing time requires container to have SYS_TIME capability or be privileged
        cmd = f"date -s '{sign}{secs} seconds'"
        res = container.exec_run(cmd)
        if res.exit_code != 0:
             return {"action": f"Failed to adjust clock (needs privileged/SYS_TIME): {res.output.decode('utf-8').strip()}"}
        return {"action": f"Adjusted clock by {offset_seconds}s on {container.name}"}

    def recover(self, container, **params):
        container.exec_run("ntpdate -u pool.ntp.org || hwclock --hctosys")
        return {"action": f"Attempted clock reset on {container.name}"}


class ProcessKillFault(FaultBase):
    name = "process_kill"
    description = "Kill a specific process inside the container"
    category = "system"
    parameters = [
        {"name": "process_name", "type": "text", "default": "python", "description": "Exact process name to kill"},
    ]

    def inject(self, container, process_name="python", **params):
        cmd = f"pkill -f '{process_name}'"
        res = container.exec_run(cmd)
        if res.exit_code != 0:
            return {"action": f"Process '{process_name}' not found or could not be killed in {container.name}"}
        return {"action": f"Killed process '{process_name}' in {container.name}"}

    def recover(self, container, **params):
        return {"action": f"Process kill fault completed on {container.name}. Manual restart may be needed if not supervised."}


# ═══════════════════════════════════════════════════════════
#  FAULT REGISTRY
# ═══════════════════════════════════════════════════════════

# Singleton registry — all available fault types
_FAULT_REGISTRY: dict[str, FaultBase] = {}


def _register_defaults():
    """Register all built-in fault types."""
    for cls in [
        CrashFault,
        LatencyFault,
        PacketLossFault,
        BandwidthThrottleFault,
        NetworkPartitionFault,
        DnsFailureFault,
        CpuStressFault,
        MemoryStressFault,
        DiskIoStressFault,
        ClockSkewFault,
        ProcessKillFault,
    ]:
        instance = cls()
        _FAULT_REGISTRY[instance.name] = instance


_register_defaults()


def get_fault(name: str) -> FaultBase:
    """Look up a fault type by name. Raises KeyError if not found."""
    if name not in _FAULT_REGISTRY:
        available = ", ".join(_FAULT_REGISTRY.keys())
        raise KeyError(f"Unknown fault type '{name}'. Available: {available}")
    return _FAULT_REGISTRY[name]


def list_faults() -> list[dict]:
    """Return metadata for all registered faults (for the frontend)."""
    return [fault.to_dict() for fault in _FAULT_REGISTRY.values()]
