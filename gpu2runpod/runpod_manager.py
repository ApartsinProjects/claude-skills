"""
RunPod Manager: Create, monitor, and terminate GPU pods via runpod Python SDK.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

KEYS_DIR = Path(__file__).parent / "keys"

_initialized = False

# Map friendly names to RunPod GPU type IDs
GPU_TYPE_IDS = {
    "H100":       "NVIDIA H100 80GB HBM3",
    "H100_SXM":   "NVIDIA H100 80GB HBM3",
    "H100_PCIE":  "NVIDIA H100 PCIe",
    "A100":       "NVIDIA A100 80GB PCIe",
    "A100_PCIE":  "NVIDIA A100 80GB PCIe",
    "A100_SXM":   "NVIDIA A100 SXM4 80GB",
    "A100_80GB":  "NVIDIA A100 80GB PCIe",
    "RTX_4090":   "NVIDIA GeForce RTX 4090",
    "RTX_3090":   "NVIDIA GeForce RTX 3090",
    "RTX_A6000":  "NVIDIA RTX A6000",
    "RTX_A5000":  "NVIDIA RTX A5000",
    "L40S":       "NVIDIA L40S",
    "L40":        "NVIDIA L40",
}

# Default image: RunPod's official PyTorch image (supports PUBLIC_KEY env var for SSH)
DEFAULT_IMAGE = "runpod/pytorch:2.2.1-py3.10-cuda12.1.1-devel-ubuntu22.04"


def _get_api_key() -> str:
    key_file = KEYS_DIR / "runpod.key"
    if key_file.exists():
        return key_file.read_text().strip()
    return os.environ.get("RUNPOD_API_KEY", "")


def _init():
    global _initialized
    if _initialized:
        return
    try:
        import runpod as _rp
    except ImportError:
        print("  [runpod] Installing runpod package...")
        subprocess.run([sys.executable, "-m", "pip", "install", "runpod"], check=True)
        import runpod as _rp
    _rp.api_key = _get_api_key()
    if not _rp.api_key:
        raise RuntimeError("RunPod API key not found. Add to keys/runpod.key or set RUNPOD_API_KEY.")
    _initialized = True


def _rp():
    _init()
    import runpod
    return runpod


def get_gpu_types() -> list[dict]:
    """Return all available GPU types with pricing."""
    return _rp().get_gpus()


def search_gpu(gpu_name: str, max_price: float = None,
               cloud_type: str = "COMMUNITY") -> dict | None:
    """Find a GPU type matching the name and price constraint.

    Returns the GPU info dict or None if not found/available.
    """
    gpu_type_id = GPU_TYPE_IDS.get(gpu_name, gpu_name.replace("_", " "))
    print(f"  [runpod] Searching for {gpu_type_id} ({cloud_type})...")

    try:
        gpus = _rp().get_gpus()
    except Exception as e:
        raise RuntimeError(f"Failed to fetch GPU types: {e}")

    for gpu in gpus:
        if gpu.get("id") == gpu_type_id:
            lowest = gpu.get("lowestPrice") or {}
            secure_ok = gpu.get("secureCloud", False)
            community_ok = gpu.get("communityCloud", False)

            if cloud_type == "SECURE" and not secure_ok:
                print(f"  [runpod] {gpu_type_id} not available in Secure Cloud")
                continue
            if cloud_type == "COMMUNITY" and not community_ok:
                print(f"  [runpod] {gpu_type_id} not available in Community Cloud, trying Secure...")
                cloud_type = "SECURE"

            price = (lowest.get("minimumBidPrice") or lowest.get("uninterruptablePrice") or 0.0)
            mem_gb = gpu.get("memoryInGb", 0)
            print(f"  [runpod] Found: {gpu_type_id} @ ~${price:.3f}/hr, {mem_gb}GB VRAM ({cloud_type})")

            if max_price is not None and price > max_price:
                print(f"  [runpod] Price ${price:.3f}/hr exceeds limit ${max_price:.3f}/hr")
                return None

            gpu["_resolved_cloud_type"] = cloud_type
            gpu["_resolved_price"] = price
            return gpu

    available = [g.get("id") for g in (gpus or []) if g.get("communityCloud") or g.get("secureCloud")]
    print(f"  [runpod] GPU '{gpu_type_id}' not found. Available: {available[:10]}")
    return None


def create_pod(name: str, gpu_type: str, image: str = DEFAULT_IMAGE,
               env_vars: dict = None, disk_gb: int = 40,
               cloud_type: str = "COMMUNITY") -> dict:
    """Create a RunPod GPU pod with SSH exposed on port 22 and TensorBoard on 6006."""
    gpu_type_id = GPU_TYPE_IDS.get(gpu_type, gpu_type.replace("_", " "))
    env = dict(env_vars or {})

    pod = _rp().create_pod(
        name=name,
        image_name=image,
        gpu_type_id=gpu_type_id,
        cloud_type=cloud_type,
        gpu_count=1,
        container_disk_in_gb=disk_gb,
        ports="22/tcp,6006/http",
        env=env,
    )
    return pod


def get_pod(pod_id: str) -> dict:
    return _rp().get_pod(pod_id)


def get_pods() -> list[dict]:
    return _rp().get_pods()


def terminate_pod(pod_id: str):
    _rp().terminate_pod(pod_id)


def stop_pod(pod_id: str):
    _rp().stop_pod(pod_id)


def is_pod_alive(pod_id: str) -> bool:
    try:
        pod = get_pod(pod_id)
        status = pod.get("desiredStatus", "")
        return status == "RUNNING"
    except Exception:
        return False


def wait_for_running(pod_id: str, timeout: int = 300) -> bool:
    """Poll until pod is RUNNING with SSH port available. Returns True on success."""
    deadline = time.time() + timeout
    last_status = ""
    last_activity = time.time()
    activity_timeout = 120

    print(f"  [runpod] Waiting for pod {pod_id} to boot (timeout={timeout}s)...")
    while time.time() < deadline:
        try:
            pod = get_pod(pod_id)
        except Exception as e:
            print(f"  [runpod] Poll error: {e}")
            time.sleep(5)
            continue

        status = pod.get("desiredStatus", "UNKNOWN")
        runtime = pod.get("runtime") or {}
        gpu_count = runtime.get("gpus")

        if status != last_status:
            print(f"  [runpod] Status: {status}" + (f" (GPU count: {len(gpu_count)})" if gpu_count else ""))
            last_status = status
            last_activity = time.time()

        if status == "RUNNING":
            ports = runtime.get("ports") or []
            ssh_port_info = next((p for p in ports if p.get("privatePort") == 22), None)
            if ssh_port_info:
                return True

        if status in ("DEAD", "FAILED", "EXITED"):
            print(f"  [runpod] Pod entered terminal state: {status}")
            return False

        if time.time() - last_activity > activity_timeout:
            print(f"  [runpod] No status change for {activity_timeout}s, aborting")
            return False

        time.sleep(5)

    print(f"  [runpod] Boot timeout after {timeout}s")
    return False


def get_connection_info(pod_id: str) -> dict:
    """Return SSH and TensorBoard connection info for a running pod."""
    pod = get_pod(pod_id)
    runtime = pod.get("runtime") or {}
    ports = runtime.get("ports") or []

    ssh_host = ""
    ssh_port = None
    tb_port = None

    for p in ports:
        private = p.get("privatePort")
        public = p.get("publicPort")
        ip = p.get("ip", "")
        if private == 22 and p.get("isIpPublic", True):
            ssh_host = ip
            ssh_port = public
        if private == 6006:
            tb_port = public

    return {
        "pod_id": pod_id,
        "ssh_host": ssh_host,
        "ssh_port": ssh_port,
        "tb_port": tb_port,
        "status": pod.get("desiredStatus", ""),
    }


def ssh_health_check(ssh_host: str, ssh_port: int, key_path: str,
                     timeout: int = 30, retries: int = 6) -> bool:
    """Verify SSH is accepting connections. Returns True on success."""
    for attempt in range(retries):
        try:
            result = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no",
                 "-o", "BatchMode=yes", "-o", "ServerAliveInterval=5",
                 "-i", key_path, "-p", str(ssh_port), f"root@{ssh_host}",
                 "echo SSH_OK"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=15,
            )
            if "SSH_OK" in result.stdout:
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        if attempt < retries - 1:
            time.sleep(5)
    return False


def estimate_cost(gpu_info: dict, estimated_minutes: float, data_gb: float = 0.1) -> dict:
    """Estimate total job cost including all phases."""
    price = gpu_info.get("_resolved_price") or 0.5
    inet_speed_gbpm = 1.0  # assume ~125 MB/s

    upload_min = data_gb / inet_speed_gbpm
    boot_min = 2.0
    setup_min = 4.0
    download_min = data_gb / inet_speed_gbpm
    train_min = estimated_minutes

    total_min = upload_min + boot_min + setup_min + train_min + download_min
    total_cost = price * (total_min / 60)

    return {
        "total_cost": round(total_cost, 4),
        "price_per_hour": price,
        "total_minutes": round(total_min, 1),
        "gpu": gpu_info.get("id", "?"),
        "phases": {
            "r2_upload": round(upload_min, 1),
            "pod_boot": round(boot_min, 1),
            "setup_and_download": round(setup_min, 1),
            "training": round(train_min, 1),
            "result_download": round(download_min, 1),
        },
    }
