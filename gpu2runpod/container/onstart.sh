#!/bin/bash
# GPU2RunPod On-Start Script for RunPod pods (uses RunPod S3-compatible storage)

# STAGE marker: updated at each section. If trap fires before STAGE=complete,
# we upload an error.json sentinel + log tail so monitor_job sees the failure
# instead of silently waiting forever.
STAGE="init"

_emit_error_sentinel() {
    local exit_code=$?
    if [ "$STAGE" = "complete" ]; then
        return
    fi
    echo "[GPU2RunPod] TRAP: stage=$STAGE exit_code=$exit_code, uploading error.json" >&2
    # Best-effort: capture last 200 lines of job log
    local log_tail=""
    if [ -f /tmp/job.log ]; then
        log_tail=$(tail -200 /tmp/job.log 2>/dev/null || echo "")
    fi
    python3 - <<PYEOF 2>/dev/null || true
import boto3, json, os, re, time
from botocore.config import Config
ep = os.environ.get('RUNPOD_STORAGE_ENDPOINT', '')
vol = os.environ.get('RUNPOD_STORAGE_VOLUME_ID', '')
pfx = os.environ.get('RUNPOD_STORAGE_JOB_PREFIX', '')
if not (ep and vol and pfx):
    raise SystemExit(0)
m = re.search(r's3api-([a-z0-9-]+)\.runpod\.io', ep)
region = m.group(1) if m else 'us-ks-2'
s3 = boto3.client('s3', endpoint_url=ep,
    aws_access_key_id=os.environ.get('RUNPOD_STORAGE_ACCESS_KEY', ''),
    aws_secret_access_key=os.environ.get('RUNPOD_STORAGE_SECRET_KEY', ''),
    region_name=region,
    config=Config(retries={'max_attempts': 3}, s3={'addressing_style': 'path'}))
log_tail = """${log_tail//\"/\\\"}"""
s3.put_object(Bucket=vol, Key=f'{pfx}/error.json', Body=json.dumps({
    'stage': '${STAGE}',
    'exit_code': ${exit_code},
    'log_tail': log_tail[-20000:],
    'timestamp': time.time(),
}))
try:
    if os.path.exists('/tmp/job.log'):
        s3.upload_file('/tmp/job.log', vol, f'{pfx}/logs/job.log')
except Exception:
    pass
PYEOF
}
trap _emit_error_sentinel EXIT

set -eo pipefail

# Source Docker container env vars — not inherited by SSH sessions
if [ -f /proc/1/environ ]; then
    _tmpenv=$(mktemp)
    while IFS= read -r -d '' _e; do
        _k="${_e%%=*}"; _v="${_e#*=}"
        case "$_k" in
            RUNPOD_STORAGE*|JOB_ID|EXPERIMENT_CMD|RESULTS_PATTERN|HF_TOKEN|HUGGING_FACE*|PUBLIC_KEY)
                printf 'export %s=%q\n' "$_k" "$_v" >> "$_tmpenv" ;;
        esac
    done < /proc/1/environ
    source "$_tmpenv"
    rm -f "$_tmpenv"
fi

SECONDS=0
ts() { echo "[GPU2RunPod] [${SECONDS}s] $1" | tee -a /tmp/job.log; }

ts "Starting job: $JOB_ID"
ts "ENV: ep=$RUNPOD_STORAGE_ENDPOINT vol=$RUNPOD_STORAGE_VOLUME_ID pfx=$RUNPOD_STORAGE_JOB_PREFIX"
ts "Image: $(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d= -f2 || echo unknown)"
ts "GPU: $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 'detecting...')"

# Pre-flight CUDA check
if command -v python3 >/dev/null 2>&1 && python3 -c "import torch" 2>/dev/null; then
    if ! python3 -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
        ts "FATAL: torch present but torch.cuda.is_available() == False"
        ts "Driver: $(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null || echo unknown)"
        ts "Torch CUDA build: $(python3 -c 'import torch; print(torch.version.cuda)' 2>/dev/null)"
        ts "Aborting before training to avoid silent billing"
        exit 42
    fi
    ts "CUDA preflight OK ($(python3 -c 'import torch; print(torch.version.cuda)'))"
fi

# 1. Install packages
STAGE="install"
ts "Installing packages..."
T0=$SECONDS
EXTRA_PKGS="boto3 transformers accelerate peft trl bitsandbytes sentence-transformers datasets requests tensorboard sentencepiece protobuf pynvml psutil"
if python3 -c "import torch" 2>/dev/null; then
    ts "torch found in base image ($(python3 -c 'import torch; print(torch.__version__)'))"
    CONSTRAINT="--constraint /tmp/torch_constraint.txt"
    python3 -c "import torch; print(f'torch=={torch.__version__}')" > /tmp/torch_constraint.txt
else
    EXTRA_PKGS="torch $EXTRA_PKGS"
    CONSTRAINT=""
    ts "torch not in base image, will install"
fi
pip install -q $CONSTRAINT $EXTRA_PKGS 2>&1 || {
    ts "WARNING: pip install had dependency conflicts, retrying core packages only"
    CORE_PKGS="boto3 transformers accelerate datasets requests tensorboard pynvml psutil"
    pip install -q $CONSTRAINT $CORE_PKGS 2>&1 || ts "WARNING: some packages failed to install (non-fatal)"
}
ts "Packages installed ($((SECONDS - T0))s)"

# 2. HuggingFace token
if [ -n "$HF_TOKEN" ]; then
    ts "Configuring HuggingFace token..."
    python3 -c "
from huggingface_hub import login
import os
token = os.environ.get('HF_TOKEN', '')
if token:
    login(token=token, add_to_git_credential=False)
    print('  HuggingFace token configured')
" 2>/dev/null || echo "  HF login skipped"
fi

# 3. Download data from RunPod storage
STAGE="download"
ts "Downloading data from RunPod storage..."
T0=$SECONDS
python3 -c "
import boto3, json, os, time
from pathlib import Path
from botocore.config import Config

ws = Path('/root/data')
ws.mkdir(parents=True, exist_ok=True)

import re as _re
endpoint = os.environ['RUNPOD_STORAGE_ENDPOINT']
m = _re.search(r's3api-([a-z0-9-]+)\.runpod\.io', endpoint)
region = m.group(1) if m else 'us-ks-2'
s3 = boto3.client('s3',
    endpoint_url=endpoint,
    aws_access_key_id=os.environ['RUNPOD_STORAGE_ACCESS_KEY'],
    aws_secret_access_key=os.environ['RUNPOD_STORAGE_SECRET_KEY'],
    region_name=region,
    config=Config(retries={'max_attempts': 5}, read_timeout=3600, connect_timeout=30, s3={'addressing_style': 'path'}))

volume_id = os.environ['RUNPOD_STORAGE_VOLUME_ID']
job_prefix = os.environ['RUNPOD_STORAGE_JOB_PREFIX']
prefix = f'{job_prefix}/data/'

count = 0
total_bytes = 0
t0 = time.time()

# Try manifest.json first — list_objects_v2 is broken on RunPod S3 (always returns empty)
manifest_keys = []
try:
    resp = s3.get_object(Bucket=volume_id, Key=f'{job_prefix}/manifest.json')
    manifest = json.loads(resp['Body'].read())
    manifest_keys = [k for k in manifest.keys() if k.startswith(prefix)]
    print(f'  [data] Using manifest.json ({len(manifest_keys)} data files)')
except Exception as e:
    print(f'  [data] manifest.json unavailable ({e}), trying listing')

if manifest_keys:
    for key in manifest_keys:
        local_name = key[len(prefix):]
        if not local_name:
            continue
        local = ws / local_name
        local.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(volume_id, key, str(local))
        size = os.path.getsize(str(local))
        count += 1
        total_bytes += size
        print(f'  {key} ({size:,} bytes)')
else:
    # Fall back to listing (may return empty on RunPod S3)
    token = None
    seen_tokens = set()
    while True:
        kwargs = {'Bucket': volume_id, 'Prefix': prefix, 'MaxKeys': 1000}
        if token:
            kwargs['ContinuationToken'] = token
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get('Contents', []):
            key = obj['Key']
            local = ws / key.replace(prefix, '', 1)
            local.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(volume_id, key, str(local))
            count += 1
            total_bytes += obj['Size']
            print(f'  {key} ({obj[\"Size\"]:,} bytes)')
        if not resp.get('IsTruncated'):
            break
        next_token = resp.get('NextContinuationToken')
        if not next_token or next_token in seen_tokens:
            break
        seen_tokens.add(next_token)
        token = next_token
elapsed = time.time() - t0
speed = total_bytes / elapsed / 1024 / 1024 if elapsed > 0 else 0
print(f'[GPU2RunPod] Downloaded {count} files ({total_bytes:,} bytes) in {elapsed:.1f}s ({speed:.1f} MB/s)')
"
ts "Data download complete ($((SECONDS - T0))s)"

# 3b. Download container helper scripts from job root (not data/ prefix)
python3 -c "
import boto3, os
from botocore.config import Config
import re as _re
endpoint = os.environ['RUNPOD_STORAGE_ENDPOINT']
m = _re.search(r's3api-([a-z0-9-]+)\.runpod\.io', endpoint)
region = m.group(1) if m else 'us-ks-2'
s3 = boto3.client('s3',
    endpoint_url=endpoint,
    aws_access_key_id=os.environ['RUNPOD_STORAGE_ACCESS_KEY'],
    aws_secret_access_key=os.environ['RUNPOD_STORAGE_SECRET_KEY'],
    region_name=region,
    config=Config(retries={'max_attempts': 5}, s3={'addressing_style': 'path'}))
volume_id = os.environ['RUNPOD_STORAGE_VOLUME_ID']
job_prefix = os.environ['RUNPOD_STORAGE_JOB_PREFIX']
for script in ['progress_reporter.py', 'gpu2runpod_observer.py']:
    key = f'{job_prefix}/{script}'
    dest = f'/root/data/{script}'
    try:
        s3.download_file(volume_id, key, dest)
        print(f'  Downloaded {script} to {dest}')
    except Exception as e:
        print(f'  Skip {script}: {e}')
"

# 4. Extra requirements
if [ -f /root/data/requirements.txt ]; then
    ts "Installing extra requirements..."
    pip install -q -r /root/data/requirements.txt
    ts "Extra requirements installed"
fi

# 5. Progress reporter
if [ -f /root/data/progress_reporter.py ]; then
    cp /root/data/progress_reporter.py /root/progress_reporter.py
fi
if [ -f /root/progress_reporter.py ]; then
    ts "Starting progress reporter"
    python3 /root/progress_reporter.py &
    REPORTER_PID=$!
else
    REPORTER_PID=""
fi

# 6. GPU observer
if [ -f /root/data/gpu2runpod_observer.py ]; then
    cp /root/data/gpu2runpod_observer.py /root/gpu2runpod_observer.py
fi
if [ -f /root/gpu2runpod_observer.py ]; then
    ts "Starting GPU observer"
    python3 /root/gpu2runpod_observer.py &
    OBSERVER_PID=$!
else
    OBSERVER_PID=""
fi

# 7. TensorBoard
ts "Starting TensorBoard on port 6006"
mkdir -p /root/data/runs
nohup tensorboard --logdir=/root/data/runs --host=0.0.0.0 --port=6006 > /dev/null 2>&1 &

# 8. Run experiment
STAGE="training"
ts "Running: $EXPERIMENT_CMD"
T0=$SECONDS
cd /root/data
set +e
eval "$EXPERIMENT_CMD" > >(tee /tmp/stdout.log) 2>&1
EXIT_CODE=$?
set -e
ts "Training finished (exit=$EXIT_CODE, ${SECONDS}s total, $((SECONDS - T0))s training)"

# 9. Stop background processes
[ -n "$REPORTER_PID" ] && kill $REPORTER_PID 2>/dev/null || true
[ -n "$OBSERVER_PID" ] && kill $OBSERVER_PID 2>/dev/null || true

# 10. Upload results to RunPod storage
STAGE="upload"
ts "Uploading results to RunPod storage..."
T0=$SECONDS
python3 -c "
import boto3, json, os, glob, time
from pathlib import Path
from botocore.config import Config

import re as _re
endpoint = os.environ['RUNPOD_STORAGE_ENDPOINT']
m = _re.search(r's3api-([a-z0-9-]+)\.runpod\.io', endpoint)
region = m.group(1) if m else 'us-ks-2'
s3 = boto3.client('s3',
    endpoint_url=endpoint,
    aws_access_key_id=os.environ['RUNPOD_STORAGE_ACCESS_KEY'],
    aws_secret_access_key=os.environ['RUNPOD_STORAGE_SECRET_KEY'],
    region_name=region,
    config=Config(retries={'max_attempts': 5}, read_timeout=3600, connect_timeout=30, s3={'addressing_style': 'path'}))

volume_id = os.environ['RUNPOD_STORAGE_VOLUME_ID']
job_prefix = os.environ['RUNPOD_STORAGE_JOB_PREFIX']
exit_code = $EXIT_CODE

uploaded = {}
total_bytes = 0
t0 = time.time()
results_dir = Path('results')
for fp in glob.glob('results/**/*', recursive=True):
    path = Path(fp)
    if path.is_file():
        rel_path = str(path.relative_to(results_dir)).replace(os.sep, '/')
        key = f'{job_prefix}/results/{rel_path}'
        s3.upload_file(str(path), volume_id, key)
        size = path.stat().st_size
        uploaded[key] = {'size': size}
        total_bytes += size
        print(f'  {rel_path} ({size:,} bytes)')

if Path('/tmp/stdout.log').exists():
    s3.upload_file('/tmp/stdout.log', volume_id, f'{job_prefix}/logs/stdout.log')

elapsed = time.time() - t0
speed = total_bytes / elapsed / 1024 / 1024 if elapsed > 0 else 0
s3.put_object(Bucket=volume_id, Key=f'{job_prefix}/done.json', Body=json.dumps({
    'status': 'success' if exit_code == 0 else 'failed',
    'exit_code': exit_code, 'files': uploaded,
    'total_bytes': total_bytes, 'timestamp': time.time()
}))
print(f'[GPU2RunPod] Uploaded {len(uploaded)} files ({total_bytes:,} bytes) in {elapsed:.1f}s ({speed:.1f} MB/s)')
"
STAGE="complete"
ts "ALL DONE (total ${SECONDS}s)"
