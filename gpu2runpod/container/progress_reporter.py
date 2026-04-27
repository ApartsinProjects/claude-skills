"""Background progress reporter. Reads /tmp/stdout.log, extracts progress, uploads to R2."""
import boto3
import json
import os
import re
import sys
import time
from pathlib import Path

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
interval = int(os.environ.get("PROGRESS_INTERVAL", "15"))

METRIC_PATTERNS = {
    "step":     r"(\d+)/(\d+)",
    "loss":     r"loss[=: ]+([0-9.]+)",
    "epoch":    r"epoch[=: ]+([0-9.]+)",
    "accuracy": r"(?:accuracy|acc|hit@1|exact_match|f1)[=: ]+([0-9.]+%?)",
    "lr":       r"(?:learning.rate|lr)[=: ]+([0-9.e-]+)",
    "val_loss": r"val(?:idation)?[_ ]loss[=: ]+([0-9.]+)",
    "val_acc":  r"val(?:idation)?[_ ](?:accuracy|acc)[=: ]+([0-9.]+%?)",
}

PHASE_PATTERNS = [
    (r"loading.*model|from_pretrained|downloading.*model", "model_loading"),
    (r"loading.*data|reading.*data|loading.*dataset",      "data_loading"),
    (r"tokeniz",                                           "tokenizing"),
    (r"downloading.*weight|downloading.*checkpoint",       "downloading_weights"),
    (r"(?:start|begin).*train|training.*(?:start|begin)",  "training"),
    (r"(?:start|begin).*eval|evaluat|validat",             "evaluating"),
    (r"saving.*model|save_pretrained|saving.*weight",      "saving_model"),
    (r"uploading.*result|uploading.*model",                "uploading_results"),
    (r"(?:all )?done|finished|complete",                   "done"),
]


def parse_progress() -> dict:
    for candidate in [Path("/tmp/stdout.log"), Path("/root/data/stdout.log")]:
        if candidate.exists():
            log = candidate
            break
    else:
        return {}

    content = log.read_text(errors="replace")
    lines = content.split("\n")
    tail = lines[-150:]

    metrics = {}
    for line in reversed(tail):
        for key, pattern in METRIC_PATTERNS.items():
            if key not in metrics:
                m = re.search(pattern, line, re.I)
                if m:
                    metrics[key] = m.group(1)
                    if key == "step" and m.lastindex and m.lastindex >= 2:
                        metrics["total"] = m.group(2)
        if len(metrics) >= 4:
            break

    current_phase = "unknown"
    for line in reversed(tail):
        for pattern, phase in PHASE_PATTERNS:
            if re.search(pattern, line, re.I):
                current_phase = phase
                break
        if current_phase != "unknown":
            break

    metrics["phase"] = current_phase
    metrics["log_lines"] = len(lines)

    recent = []
    for line in reversed(tail):
        line = line.strip()
        if line and not line.startswith("  ") and len(line) > 5:
            recent.append(line)
            if len(recent) >= 5:
                break
    metrics["recent_lines"] = list(reversed(recent))
    return metrics


while True:
    try:
        progress = parse_progress()
        progress["timestamp"] = time.time()
        progress["job_id"] = os.environ.get("JOB_ID", "")

        s3.put_object(
            Bucket=volume_id, Key=f"{job_prefix}/progress.json",
            Body=json.dumps(progress),
        )

        for log_path in [Path("/tmp/stdout.log"), Path("/root/data/stdout.log")]:
            if log_path.exists():
                content = log_path.read_bytes()
                if len(content) > 100000:
                    content = b"[...truncated...]\n" + content[-100000:]
                s3.put_object(
                    Bucket=volume_id,
                    Key=f"{job_prefix}/logs/{log_path.name}",
                    Body=content,
                )
                break

    except Exception as e:
        print(f"[progress] error: {e}", file=sys.stderr)

    time.sleep(interval)
