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
        output = result.stdout.strip()
        if "error" in output.lower() or "<html" in output.lower():
            raise RuntimeError(f"vast.ai returned non-JSON response: {output[:200]}")
        return output


def _shell_escape(value: str) -> str:
    """Escape a value for use in -e K=V env var format."""
    s = str(value)
    if not s or any(c in s for c in " \t\n'\"\\$`!#&|;(){}"):
        return "'" + s.replace("'", "'\\''") + "'"
    return s


def search_gpu(gpu_name: str = "RTX_4090", max_price: float = 0.50,
               disk_gb: int = 30, num_gpus: int = 1) -> list[dict]:
    """Search for available GPU offers."""
    print(f"  [vast] Querying offers: {gpu_name} x{num_gpus}, <=${max_price}/hr, {disk_gb}GB disk...")
    query = f"gpu_name={gpu_name} num_gpus={num_gpus} disk_space>={disk_gb} dph<={max_price} inet_down>=200 reliability>0.95"
    results = _vast_cmd(["search", "offers", "--raw", query])
    if isinstance(results, list):
        sorted_results = sorted(results, key=lambda x: x.get("dph_total", 999))
        print(f"  [vast] Found {len(sorted_results)} matching offers")
        return sorted_results
    print("  [vast] No offers returned")
    return []


def create_instance(offer_id: int, docker_image: str, env_vars: dict = None,
                    onstart_cmd: str = "", disk_gb: int = 30) -> dict:
    """Create a new instance from an offer."""
    print(f"  [vast] Creating instance from offer {offer_id} (image={docker_image}, disk={disk_gb}GB)...")
    args = [
        "create", "instance", str(offer_id),
        "--image", docker_image,
        "--disk", str(disk_gb),
        "--raw",
    ]
    if onstart_cmd:
        args.extend(["--onstart-cmd", onstart_cmd])
    if env_vars:
        env_str = " ".join(f"-e {k}={_shell_escape(v)}" for k, v in env_vars.items())
        args.extend(["--env", env_str])

    result = _vast_cmd(args)
    instance_id = result.get("new_contract") or result.get("instance_id") if isinstance(result, dict) else None
    print(f"  [vast] Instance created: {instance_id}")
    return result


def get_instance(instance_id: int) -> dict:
    """Get instance details."""
    results = _vast_cmd(["show", "instance", str(instance_id), "--raw"])
    return results


def destroy_instance(instance_id: int):
    """Destroy an instance."""
    print(f"  [vast] Destroying instance {instance_id}...")
    result = _vast_cmd(["destroy", "instance", str(instance_id)])
    print(f"  [vast] Instance {instance_id} destroyed")
    return result


def list_instances() -> list[dict]:
    """List all active instances."""
    return _vast_cmd(["show", "instances", "--raw"])


def get_logs(instance_id: int, tail: int = 50) -> str:
    """Fetch recent logs from a running instance."""
    api_key = _get_api_key()
    try:
        result = subprocess.run(
            ["vastai", "--api-key", api_key, "logs", str(instance_id), "--tail", str(tail)],
            capture_output=True, text=True, timeout=15,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def wait_for_running(instance_id: int, timeout: int = 300) -> bool:
    """Wait for instance to reach 'running' state."""
    print(f"  [vast] Waiting for instance {instance_id} to boot (timeout={timeout}s)...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            info = get_instance(instance_id)
            status = info.get("actual_status", "?") if isinstance(info, dict) else "?"
            elapsed = int(time.time() - start)
            print(f"\r  [vast] Status: {status} ({elapsed}s elapsed)    ", end="", flush=True)
            if status == "running":
                print()
                return True
        except Exception:
            pass
        time.sleep(10)
    print(f"\n  [vast] Timed out after {timeout}s")
    return False
