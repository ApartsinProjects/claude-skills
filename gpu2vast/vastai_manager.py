"""
vast.ai Manager: Search, create, monitor, destroy GPU instances.
Uses vast.ai Python SDK (pip install vastai).
"""

import json
import subprocess
import sys
import time
from pathlib import Path

KEYS_DIR = Path(__file__).parent / "keys"


def _get_api_key():
    key_file = KEYS_DIR / "vastai.key"
    if key_file.exists():
        return key_file.read_text().strip()
    import os
    return os.environ.get("VASTAI_API_KEY", "")


def _ensure_vastai():
    """Check vast CLI is installed."""
    try:
        subprocess.run(["vastai", "--version"], capture_output=True, timeout=5)
    except FileNotFoundError:
        print("vast.ai CLI not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "vastai"], check=True)


def _vast_cmd(args: list[str]) -> dict | list | str:
    """Run vastai CLI command and return parsed output."""
    _ensure_vastai()
    api_key = _get_api_key()
    cmd = ["vastai", "--api-key", api_key] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"vast.ai error: {result.stderr}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.stdout.strip()


def search_gpu(gpu_name: str = "RTX_4090", max_price: float = 0.50,
               disk_gb: int = 30, num_gpus: int = 1) -> list[dict]:
    """Search for available GPU offers."""
    query = f"gpu_name={gpu_name} num_gpus={num_gpus} disk_space>={disk_gb} dph<={max_price} inet_down>=200 reliability>0.95"
    results = _vast_cmd(["search", "offers", "--raw", query])
    if isinstance(results, list):
        return sorted(results, key=lambda x: x.get("dph_total", 999))
    return []


def create_instance(offer_id: int, docker_image: str, env_vars: dict = None,
                    onstart_cmd: str = "", disk_gb: int = 30) -> dict:
    """Create a new instance from an offer."""
    args = [
        "create", "instance", str(offer_id),
        "--image", docker_image,
        "--disk", str(disk_gb),
        "--raw",
    ]
    if onstart_cmd:
        args.extend(["--onstart-cmd", onstart_cmd])
    if env_vars:
        env_str = " ".join(f"-e {k}={v}" for k, v in env_vars.items())
        args.extend(["--env", env_str])

    return _vast_cmd(args)


def get_instance(instance_id: int) -> dict:
    """Get instance details."""
    results = _vast_cmd(["show", "instance", str(instance_id), "--raw"])
    return results


def destroy_instance(instance_id: int):
    """Destroy an instance."""
    return _vast_cmd(["destroy", "instance", str(instance_id)])


def list_instances() -> list[dict]:
    """List all active instances."""
    return _vast_cmd(["show", "instances", "--raw"])


def wait_for_running(instance_id: int, timeout: int = 300) -> bool:
    """Wait for instance to reach 'running' state."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            info = get_instance(instance_id)
            if isinstance(info, dict) and info.get("actual_status") == "running":
                return True
        except Exception:
            pass
        time.sleep(10)
    return False
