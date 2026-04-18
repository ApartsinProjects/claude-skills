"""
vast.ai Manager: Search, create, monitor, destroy GPU instances.
Uses vast.ai Python API (pip install vastai).
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

KEYS_DIR = Path(__file__).parent / "keys"

_client = None


def _get_client():
    """Get or create a VastAI API client."""
    global _client
    if _client is not None:
        return _client
    try:
        from vastai.api.client import VastClient
    except ImportError:
        print("  [vast] Installing vastai package...")
        subprocess.run([sys.executable, "-m", "pip", "install", "vastai"], check=True)
        from vastai.api.client import VastClient

    api_key = _get_api_key()
    _client = VastClient(api_key=api_key)
    return _client


def _get_api_key():
    key_file = KEYS_DIR / "vastai.key"
    if key_file.exists():
        return key_file.read_text().strip()
    return os.environ.get("VASTAI_API_KEY", "")


def search_gpu(gpu_name: str = "RTX_4090", max_price: float = 0.50,
               disk_gb: int = 30, num_gpus: int = 1,
               offer_type: str = "on-demand") -> list[dict]:
    """Search for available GPU offers. Accepts both 'RTX_4090' and 'RTX 4090' formats.

    offer_type: "on-demand" (default) or "bid" (spot/interruptible, 50-70% cheaper)
    """
    from vastai.api import offers as offers_api
    api_gpu_name = gpu_name.replace("_", " ")
    type_label = "spot" if offer_type == "bid" else "on-demand"
    print(f"  [vast] Querying {type_label} offers: {api_gpu_name} x{num_gpus}, <=${max_price}/hr, {disk_gb}GB disk...")
    client = _get_client()
    query = {
        "gpu_name": {"eq": api_gpu_name},
        "num_gpus": {"eq": num_gpus},
        "disk_space": {"gte": disk_gb},
        "dph_total": {"lte": max_price},
        "inet_down": {"gte": 200},
        "reliability2": {"gte": 0.95},
    }
    try:
        results = offers_api.search_offers(client, query=query, storage=float(disk_gb),
                                           offer_type=offer_type)
    except Exception as e:
        print(f"  [vast] API search failed ({e}), falling back to CLI...")
        results = _search_gpu_cli(gpu_name, max_price, disk_gb, num_gpus)

    if isinstance(results, list) and results:
        scored = sorted(results, key=lambda x: _cost_score(x))
        best = scored[0]
        print(f"  [vast] Found {len(scored)} offers, best: "
              f"{best.get('gpu_name')} ${best.get('dph_total', 0):.3f}/hr "
              f"RAM={best.get('gpu_ram', 0):.0f}GB "
              f"Net={best.get('inet_down', 0):.0f}Mbps "
              f"Score={_cost_score(best):.3f}")
        return scored
    print("  [vast] No offers returned")
    return []


def estimate_cost(offer: dict, estimated_minutes: float) -> dict:
    """Estimate total job cost for a given offer and runtime."""
    price_per_hour = offer.get("dph_total", 0)
    hours = estimated_minutes / 60
    compute_cost = price_per_hour * hours
    storage_cost = 0.0  # R2 free tier
    return {
        "compute_cost": round(compute_cost, 4),
        "storage_cost": storage_cost,
        "total_cost": round(compute_cost + storage_cost, 4),
        "price_per_hour": price_per_hour,
        "estimated_minutes": estimated_minutes,
        "gpu": offer.get("gpu_name", "?"),
    }


# ── Docker Image Selection ──

DOCKER_IMAGES = {
    "pytorch": {
        "image": "vastai/pytorch",
        "packages": ["torch", "torchvision"],
        "description": "Pre-cached PyTorch (fastest boot)",
    },
    "transformers": {
        "image": "huggingface/transformers-pytorch-gpu",
        "packages": ["torch", "transformers", "accelerate", "datasets", "tokenizers"],
        "description": "HuggingFace Transformers + PyTorch",
    },
    "full-ml": {
        "image": "nvcr.io/nvidia/pytorch:24.01-py3",
        "packages": ["torch", "torchvision", "numpy", "scipy", "pandas"],
        "description": "NVIDIA NGC full ML stack",
    },
    "cuda": {
        "image": "nvidia/cuda:12.1.0-runtime-ubuntu22.04",
        "packages": [],
        "description": "Base CUDA runtime (install everything yourself)",
    },
}


def select_image(script_path: str = None, requirements: list[str] = None) -> str:
    """Select the best Docker image based on script imports or explicit requirements.

    Returns the docker image string. Examines the script for imports to determine
    which pre-built image saves the most pip install time.
    """
    needed = set(requirements or [])

    if script_path:
        try:
            content = Path(script_path).read_text(errors="replace")
            import_map = {
                "transformers": "transformers",
                "from transformers": "transformers",
                "accelerate": "accelerate",
                "datasets": "datasets",
                "peft": "peft",
                "trl": "trl",
                "sentence_transformers": "sentence-transformers",
                "bitsandbytes": "bitsandbytes",
                "torch": "torch",
                "tensorflow": "tensorflow",
                "jax": "jax",
            }
            for pattern, pkg in import_map.items():
                if pattern in content:
                    needed.add(pkg)
        except Exception:
            pass

    # Score each image by how many needed packages it already has
    best_image = "vastai/pytorch"
    best_score = 0

    for name, info in DOCKER_IMAGES.items():
        provided = set(info["packages"])
        overlap = len(needed & provided)
        if overlap > best_score:
            best_score = overlap
            best_image = info["image"]

    # If transformers/peft/trl needed, use HF image
    hf_packages = {"transformers", "accelerate", "peft", "trl", "datasets", "sentence-transformers"}
    if needed & hf_packages:
        best_image = DOCKER_IMAGES["transformers"]["image"]

    print(f"  [vast] Selected image: {best_image} (needed: {', '.join(sorted(needed)) or 'base only'})")
    return best_image


def _cost_score(offer: dict) -> float:
    """Score an offer by cost-effectiveness. Lower is better.

    Weighs price heavily but penalizes slow network, low RAM, and low reliability,
    since those increase total job cost (longer transfers, OOM retries, failures).
    """
    price = offer.get("dph_total", 999)
    inet_down = max(offer.get("inet_down", 1), 1)
    inet_up = max(offer.get("inet_up", 1), 1)
    gpu_ram = max(offer.get("gpu_ram", 1), 1)
    reliability = max(offer.get("reliability2", 0.5), 0.01)
    dlperf = max(offer.get("dlperf", 1), 0.01)

    # Normalize: penalize slow network (data transfer time adds cost)
    net_penalty = 100.0 / min(inet_down, 1000) + 50.0 / min(inet_up, 500)
    # Penalize low reliability (higher chance of job failure = wasted money)
    reliability_penalty = 0.1 / reliability
    # Bonus for higher GPU RAM and DL performance
    ram_bonus = -0.001 * min(gpu_ram, 80)
    perf_bonus = -0.001 * min(dlperf, 50)

    return price + net_penalty * 0.01 + reliability_penalty + ram_bonus + perf_bonus


def _search_gpu_cli(gpu_name, max_price, disk_gb, num_gpus):
    """Fallback: search via CLI if API query format fails."""
    api_key = _get_api_key()
    query = f"gpu_name={gpu_name} num_gpus={num_gpus} disk_space>={disk_gb} dph<={max_price} inet_down>=200 reliability>0.95"
    cmd = ["vastai", "--api-key", api_key, "search", "offers", "--raw", query]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"vast.ai search error: {result.stderr}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def create_instance(offer_id: int, docker_image: str, env_vars: dict = None,
                    onstart_cmd: str = "", disk_gb: int = 30) -> dict:
    """Create a new instance from an offer."""
    from vastai.api import instances
    print(f"  [vast] Creating instance from offer {offer_id} (image={docker_image}, disk={disk_gb}GB)...")
    client = _get_client()

    result = instances.create_instance(
        client, id=offer_id, image=docker_image, disk=disk_gb,
        env=env_vars, onstart_cmd=onstart_cmd or None,
    )

    instance_id = None
    if isinstance(result, dict):
        instance_id = result.get("new_contract") or result.get("instance_id")
    print(f"  [vast] Instance created: {instance_id}")
    return result


def get_instance(instance_id: int) -> dict:
    """Get instance details."""
    from vastai.api import instances
    client = _get_client()
    try:
        return instances.show_instance(client, id=instance_id)
    except (TypeError, KeyError, AttributeError):
        return {"actual_status": "loading", "status_msg": "instance loading (metadata not yet available)"}
    except Exception as e:
        if "not found" in str(e).lower() or "404" in str(e):
            return {}
        raise


def destroy_instance(instance_id: int):
    """Destroy an instance."""
    from vastai.api import instances
    print(f"  [vast] Destroying instance {instance_id}...")
    client = _get_client()
    result = instances.destroy_instance(client, id=instance_id)
    print(f"  [vast] Instance {instance_id} destroyed")
    return result


def list_instances() -> list[dict]:
    """List all active instances."""
    from vastai.api import instances
    client = _get_client()
    return instances.show_instances(client)


def get_logs(instance_id: int, tail: int = 50) -> str:
    """Fetch recent logs from a running instance."""
    from vastai.api import instances
    client = _get_client()
    try:
        result = instances.logs(client, instance_id=instance_id, tail=tail)
        if isinstance(result, str):
            return result.strip()
        if isinstance(result, (list, dict)):
            return json.dumps(result)
        return str(result).strip() if result else ""
    except Exception:
        return ""


def wait_for_running(instance_id: int, timeout: int = 300) -> bool:
    """Wait for instance to reach 'running' state. Raises on error states."""
    print(f"  [vast] Waiting for instance {instance_id} to boot (timeout={timeout}s)...")
    start = time.time()
    error_states = {"exited", "stopped"}
    while time.time() - start < timeout:
        try:
            info = get_instance(instance_id)
            if not isinstance(info, dict) or not info:
                elapsed = int(time.time() - start)
                print(f"\r  [vast] Instance {instance_id} not found ({elapsed}s)    ", end="", flush=True)
                time.sleep(10)
                continue

            status = info.get("actual_status", "?")
            status_msg = info.get("status_msg", "")
            elapsed = int(time.time() - start)
            display = f"{status}"
            if status_msg:
                display += f" [{status_msg[:60]}]"
            print(f"\r  [vast] Status: {display} ({elapsed}s elapsed)    ", end="", flush=True)

            if status == "running":
                print()
                return True

            if status in error_states:
                print(f"\n  [vast] Instance entered error state: {status}")
                if status_msg:
                    print(f"  [vast] Message: {status_msg}")
                raise RuntimeError(f"Instance {instance_id} failed: {status}. {status_msg}")

            if status_msg and any(kw in status_msg.lower() for kw in [
                "error", "invalid", "not started loading", "docker image",
                "has not started", "failed", "cannot"
            ]):
                print(f"\n  [vast] Instance error detected: {status_msg}")
                raise RuntimeError(f"Instance {instance_id} failed: {status_msg}")

        except RuntimeError:
            raise
        except Exception:
            pass
        time.sleep(10)
    print(f"\n  [vast] Timed out after {timeout}s")
    return False


def is_instance_alive(instance_id: int) -> bool:
    """Check if an instance still exists and is not destroyed."""
    try:
        info = get_instance(instance_id)
        if not isinstance(info, dict) or not info:
            return False
        status = info.get("actual_status", "")
        return status not in {"", "exited", "stopped"}
    except Exception:
        return False


# ── SSH Key Management ──

def ensure_ssh_key() -> str:
    """Generate SSH keypair if needed and register with vast.ai. Returns public key."""
    ssh_dir = KEYS_DIR / "ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)
    private_key = ssh_dir / "gpu2vast_ed25519"
    public_key = ssh_dir / "gpu2vast_ed25519.pub"

    if not private_key.exists():
        print("  [vast] Generating SSH keypair...")
        subprocess.run([
            "ssh-keygen", "-t", "ed25519", "-f", str(private_key),
            "-N", "", "-C", "gpu2vast-auto"
        ], check=True, capture_output=True)
        print(f"  [vast] SSH key generated: {private_key}")

    pub_key_text = public_key.read_text().strip()

    # Register with vast.ai if not already registered
    existing = list_ssh_keys()
    already_registered = any(pub_key_text in k.get("public_key", "") for k in existing)

    if not already_registered:
        print("  [vast] Registering SSH key with vast.ai...")
        register_ssh_key(pub_key_text)
        print("  [vast] SSH key registered")
    else:
        print("  [vast] SSH key already registered with vast.ai")

    return pub_key_text


def get_ssh_private_key_path() -> Path:
    """Return path to SSH private key, generating if needed."""
    ensure_ssh_key()
    return KEYS_DIR / "ssh" / "gpu2vast_ed25519"


def list_ssh_keys() -> list[dict]:
    """List SSH keys registered with vast.ai."""
    from vastai.api import keys
    client = _get_client()
    try:
        result = keys.show_ssh_keys(client)
        return result if isinstance(result, list) else []
    except Exception:
        return []


def register_ssh_key(public_key: str) -> dict:
    """Register an SSH public key with vast.ai."""
    from vastai.api import keys
    client = _get_client()
    return keys.create_ssh_key(client, ssh_key=public_key)


def attach_ssh_to_instance(instance_id: int, public_key: str = None) -> dict:
    """Attach SSH key to a running instance."""
    from vastai.api import keys
    client = _get_client()
    if public_key is None:
        public_key = ensure_ssh_key()
    return keys.attach_ssh(client, instance_id=instance_id, ssh_key=public_key)


def ssh_command(instance_id: int) -> str:
    """Get SSH command to connect to an instance."""
    info = get_instance(instance_id)
    if not isinstance(info, dict):
        return ""
    ssh_host = info.get("ssh_host", "")
    ssh_port = info.get("ssh_port", "")
    private_key = get_ssh_private_key_path()
    if ssh_host and ssh_port:
        return f"ssh -i {private_key} -p {ssh_port} root@{ssh_host}"
    return ""


def get_connection_info(instance_id: int) -> dict:
    """Get all connection details for a running instance (SSH, ports, IP)."""
    info = get_instance(instance_id)
    if not isinstance(info, dict):
        return {}

    ssh_host = info.get("ssh_host", "")
    ssh_port = info.get("ssh_port", "")
    public_ip = info.get("public_ipaddr", "")
    ports = info.get("ports", {})
    private_key = get_ssh_private_key_path()

    result = {
        "ssh_host": ssh_host,
        "ssh_port": ssh_port,
        "public_ip": public_ip,
        "ssh_command": f"ssh -i {private_key} -p {ssh_port} root@{ssh_host}" if ssh_host else "",
        "port_mappings": {},
    }

    # Parse port mappings: vast.ai maps container ports to host ports
    # Format varies: could be dict like {"8080/tcp": [{"HostPort": "12345"}]}
    if isinstance(ports, dict):
        for container_port, mappings in ports.items():
            if isinstance(mappings, list) and mappings:
                host_port = mappings[0].get("HostPort", "")
                if host_port:
                    result["port_mappings"][container_port] = {
                        "host_port": host_port,
                        "url": f"http://{public_ip}:{host_port}",
                    }

    return result


def port_forward(instance_id: int, remote_port: int, local_port: int = None) -> str:
    """Get SSH port forwarding command. Maps remote_port on instance to local_port on your machine."""
    if local_port is None:
        local_port = remote_port
    info = get_instance(instance_id)
    if not isinstance(info, dict):
        return ""
    ssh_host = info.get("ssh_host", "")
    ssh_port = info.get("ssh_port", "")
    private_key = get_ssh_private_key_path()
    if ssh_host and ssh_port:
        cmd = (f"ssh -i {private_key} -p {ssh_port} root@{ssh_host} "
               f"-L {local_port}:localhost:{remote_port} -N")
        return cmd
    return ""


def open_tunnel(instance_id: int, remote_port: int, local_port: int = None):
    """Open an SSH tunnel in the background. Returns the subprocess."""
    if local_port is None:
        local_port = remote_port
    info = get_instance(instance_id)
    if not isinstance(info, dict):
        raise RuntimeError(f"Instance {instance_id} not found")
    ssh_host = info.get("ssh_host", "")
    ssh_port = info.get("ssh_port", "")
    private_key = get_ssh_private_key_path()
    if not ssh_host or not ssh_port:
        raise RuntimeError(f"No SSH info for instance {instance_id}")

    print(f"  [vast] Opening tunnel: localhost:{local_port} -> instance:{remote_port}")
    proc = subprocess.Popen(
        ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
         "-i", str(private_key), "-p", str(ssh_port), f"root@{ssh_host}",
         "-L", f"{local_port}:localhost:{remote_port}", "-N"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    print(f"  [vast] Tunnel open: http://localhost:{local_port}")
    return proc
