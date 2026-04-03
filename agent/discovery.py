import platform
import socket
import psutil

class HeuristicDiscovery:
    def __init__(self):
        try:
            import docker
            self.docker_client = docker.from_env()
        except:
            self.docker_client = None

    def discover_environment(self):
        profile = {
            "os": platform.system(),
            "release": platform.release(),
            "hostname": socket.gethostname(),
            "containers": [],
            "processes": [],
            "capabilities": ["simulate_network_delay", "spike_cpu_memory"] 
        }

        # 1. Dynamic Docker Container Discovery
        if self.docker_client:
            profile["capabilities"].append("crash_container")
            try:
                for container in self.docker_client.containers.list():
                    profile["containers"].append({
                        "id": container.short_id,
                        "name": container.name,
                        "status": container.status
                    })
            except Exception as e:
                profile["docker_error"] = str(e)

        # 2. Dynamic Process Identification (Looking for critical runtimes natively)
        try:
            for proc in psutil.process_iter(['name']):
                name = str(proc.info['name']).lower()
                # Identifying common distributed frameworks
                if name in ['python', 'python3', 'node', 'java', 'postgres', 'mysql', 'nginx', 'envoy']:
                    profile["processes"].append(name)
        except Exception:
            pass
            
        profile["processes"] = list(set(profile["processes"]))

        return profile
