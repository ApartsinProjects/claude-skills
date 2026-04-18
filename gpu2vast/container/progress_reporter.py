"""Background progress reporter. Reads stdout.log, extracts progress, uploads to R2."""
import boto3, json, os, re, time, subprocess
from pathlib import Path

s3 = boto3.client("s3",
    endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ["R2_ACCESS_KEY"],
    aws_secret_access_key=os.environ["R2_SECRET_KEY"],
    region_name="auto",
)
bucket = os.environ["R2_BUCKET"]
interval = int(os.environ.get("PROGRESS_INTERVAL", "30"))

PATTERNS = {
    "step": r"(\d+)/(\d+)",
    "loss": r"loss[=: ]+([0-9.]+)",
    "epoch": r"epoch[=: ]+([0-9.]+)",
    "accuracy": r"(?:accuracy|hit@1|exact)[=: ]+([0-9.]+%?)",
}

def get_gpu_info():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        parts = result.stdout.strip().split(", ")
        return {"gpu_util": int(parts[0]), "mem_used": int(parts[1]),
                "mem_total": int(parts[2]), "temp": int(parts[3])}
    except:
        return {}

def parse_last_progress():
    log = Path("/workspace/stdout.log")
    if not log.exists():
        return {}
    lines = log.read_text(errors="replace").split("\n")
    progress = {}
    for line in reversed(lines[-100:]):
        for key, pattern in PATTERNS.items():
            if key not in progress:
                m = re.search(pattern, line, re.I)
                if m:
                    progress[key] = m.group(1)
                    if key == "step" and m.group(2):
                        progress["total"] = m.group(2)
        if len(progress) >= 3:
            break
    return progress

while True:
    try:
        progress = parse_last_progress()
        progress["gpu"] = get_gpu_info()
        progress["timestamp"] = time.time()
        progress["job_id"] = os.environ.get("JOB_ID", "")

        s3.put_object(
            Bucket=bucket, Key="progress.json",
            Body=json.dumps(progress),
        )
    except Exception as e:
        pass

    time.sleep(interval)
