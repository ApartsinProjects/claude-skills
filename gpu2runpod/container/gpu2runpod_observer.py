"""GPU observer using pynvml for real-time metrics. Uploads to R2 every 10s."""
import boto3
import json
import os
import sys
import time

import re as _re
from botocore.config import Config

_ep = os.environ["RUNPOD_STORAGE_ENDPOINT"]
_m = _re.search(r"s3api-([a-z0-9-]+)\.runpod\.io", _ep)
_region = _m.group(1) if _m else "us-ks-2"
s3 = boto3.client(
    "s3",
    endpoint_url=_ep,
    aws_access_key_id=os.environ["RUNPOD_STORAGE_ACCESS_KEY"],
    aws_secret_access_key=os.environ["RUNPOD_STORAGE_SECRET_KEY"],
    region_name=_region,
    config=Config(retries={"max_attempts": 3}, connect_timeout=10),
)
volume_id = os.environ["RUNPOD_STORAGE_VOLUME_ID"]
job_prefix = os.environ["RUNPOD_STORAGE_JOB_PREFIX"]
interval = int(os.environ.get("OBSERVER_INTERVAL", "10"))

try:
    import pynvml
    pynvml.nvmlInit()
    NVML_OK = True
except Exception as e:
    print(f"[observer] pynvml init failed: {e}", file=sys.stderr)
    NVML_OK = False

try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    PSUTIL_OK = False


def get_gpu_metrics() -> dict:
    if not NVML_OK:
        return {}
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        try:
            power_mw = pynvml.nvmlDeviceGetPowerUsage(handle)
            power_limit_mw = pynvml.nvmlDeviceGetPowerManagementLimitConstraints(handle)[1]
            power_w = round(power_mw / 1000, 1)
            power_limit_w = round(power_limit_mw / 1000, 1)
        except pynvml.NVMLError:
            power_w = None
            power_limit_w = None
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode()
        return {
            "name": name,
            "gpu_util_pct": util.gpu,
            "mem_util_pct": util.memory,
            "mem_used_gb": round(mem.used / 1024**3, 2),
            "mem_total_gb": round(mem.total / 1024**3, 2),
            "mem_free_gb": round(mem.free / 1024**3, 2),
            "temperature_c": temp,
            "power_w": power_w,
            "power_limit_w": power_limit_w,
        }
    except Exception as e:
        return {"error": str(e)}


def get_system_metrics() -> dict:
    if not PSUTIL_OK:
        return {}
    try:
        vm = psutil.virtual_memory()
        return {
            "cpu_util_pct": psutil.cpu_percent(interval=0.1),
            "ram_used_gb": round(vm.used / 1024**3, 2),
            "ram_total_gb": round(vm.total / 1024**3, 2),
            "ram_util_pct": vm.percent,
        }
    except Exception as e:
        return {"error": str(e)}


history = []
MAX_HISTORY = 60

while True:
    try:
        gpu = get_gpu_metrics()
        sys_metrics = get_system_metrics()
        record = {
            "timestamp": time.time(),
            "job_id": os.environ.get("JOB_ID", ""),
            "gpu": gpu,
            "system": sys_metrics,
        }
        history.append(record)
        if len(history) > MAX_HISTORY:
            history = history[-MAX_HISTORY:]

        # Upload current + history
        payload = {
            "current": record,
            "history": history,
            "samples": len(history),
        }
        s3.put_object(
            Bucket=volume_id, Key=f"{job_prefix}/gpu_metrics.json",
            Body=json.dumps(payload),
        )

        # Print summary to stdout so it appears in job log
        if gpu:
            util = gpu.get("gpu_util_pct", "?")
            mem_used = gpu.get("mem_used_gb", "?")
            mem_total = gpu.get("mem_total_gb", "?")
            temp = gpu.get("temperature_c", "?")
            power = gpu.get("power_w", "?")
            print(
                f"[observer] GPU: {util}% util, {mem_used}/{mem_total}GB VRAM, "
                f"{temp}C, {power}W",
                flush=True,
            )

    except Exception as e:
        print(f"[observer] error: {e}", file=sys.stderr)

    time.sleep(interval)
