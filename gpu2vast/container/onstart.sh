#!/bin/bash
# GPU2Vast On-Start Script for vast.ai instances
# Runs automatically when instance boots.
set -eo pipefail

echo "[GPU2Vast] Starting job: $JOB_ID"
echo "[GPU2Vast] Image: $(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d= -f2 || echo unknown)"

# 1. Install Python packages (using uv if available, else pip)
echo "[GPU2Vast] Installing packages..."
if command -v uv &> /dev/null; then
    uv pip install --system boto3 transformers accelerate peft trl \
        bitsandbytes sentence-transformers datasets requests 2>&1 | tail -3
else
    pip install --no-cache-dir boto3 transformers accelerate peft trl \
        bitsandbytes sentence-transformers datasets requests 2>&1 | tail -3
fi
echo "[GPU2Vast] Packages installed"

# 2. Configure HuggingFace token if provided
if [ -n "$HF_TOKEN" ]; then
    echo "[GPU2Vast] Configuring HuggingFace token..."
    python3 -c "
from huggingface_hub import login
import os
token = os.environ.get('HF_TOKEN', '')
if token:
    login(token=token, add_to_git_credential=False)
    print('  HuggingFace token configured')
" 2>/dev/null || echo "  HF login skipped (huggingface_hub not available)"
fi

# 3. Download experiment data from R2
echo "[GPU2Vast] Downloading data from R2..."
python3 -c "
import boto3, json, os
from pathlib import Path

ws = Path('/workspace/data')
ws.mkdir(parents=True, exist_ok=True)

s3 = boto3.client('s3',
    endpoint_url=f'https://{os.environ[\"R2_ACCOUNT_ID\"]}.r2.cloudflarestorage.com',
    aws_access_key_id=os.environ['R2_ACCESS_KEY'],
    aws_secret_access_key=os.environ['R2_SECRET_KEY'],
    region_name='auto')

bucket = os.environ['R2_BUCKET']
paginator = s3.get_paginator('list_objects_v2')
count = 0
total_bytes = 0
for page in paginator.paginate(Bucket=bucket, Prefix='data/'):
    for obj in page.get('Contents', []):
        key = obj['Key']
        local = ws / key.replace('data/', '', 1)
        local.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(bucket, key, str(local))
        count += 1
        total_bytes += obj['Size']
        print(f'  Downloaded: {key} ({obj[\"Size\"]:,} bytes)')
print(f'[GPU2Vast] Downloaded {count} files ({total_bytes:,} bytes total)')
"

# 4. Install extra requirements if present
if [ -f /workspace/data/requirements.txt ]; then
    echo "[GPU2Vast] Installing extra requirements..."
    pip install -q -r /workspace/data/requirements.txt
    echo "[GPU2Vast] Extra requirements installed"
fi

# 5. Copy and start progress reporter + checkpoint streamer in background
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/progress_reporter.py" ]; then
    cp "$SCRIPT_DIR/progress_reporter.py" /workspace/progress_reporter.py
elif [ -f /workspace/data/progress_reporter.py ]; then
    cp /workspace/data/progress_reporter.py /workspace/progress_reporter.py
fi

if [ -f /workspace/progress_reporter.py ]; then
    echo "[GPU2Vast] Starting progress reporter..."
    python3 /workspace/progress_reporter.py &
    REPORTER_PID=$!
else
    echo "[GPU2Vast] Warning: progress_reporter.py not found, inline fallback"
    REPORTER_PID=""
fi

# 6. Start TensorBoard in background (port 6006)
echo "[GPU2Vast] Starting TensorBoard on port 6006..."
pip install -q tensorboard 2>/dev/null
mkdir -p /workspace/data/runs
tensorboard --logdir=/workspace/data/runs --host=0.0.0.0 --port=6006 2>/dev/null &
TB_PID=$!
echo "[GPU2Vast] TensorBoard running (PID=$TB_PID, port=6006)"

# 7. Run experiment
echo "[GPU2Vast] Running: $EXPERIMENT_CMD"
cd /workspace/data
eval "$EXPERIMENT_CMD" 2>&1 | tee /workspace/stdout.log
EXIT_CODE=${PIPESTATUS[0]}

# 8. Stop reporter
if [ -n "$REPORTER_PID" ]; then
    kill $REPORTER_PID 2>/dev/null || true
fi

# 8. Upload all results to R2
echo "[GPU2Vast] Uploading results..."
python3 -c "
import boto3, json, os, glob, hashlib, time
from pathlib import Path

s3 = boto3.client('s3',
    endpoint_url=f'https://{os.environ[\"R2_ACCOUNT_ID\"]}.r2.cloudflarestorage.com',
    aws_access_key_id=os.environ['R2_ACCESS_KEY'],
    aws_secret_access_key=os.environ['R2_SECRET_KEY'],
    region_name='auto')
bucket = os.environ['R2_BUCKET']
pattern = os.environ.get('RESULTS_PATTERN', 'results/*')
exit_code = $EXIT_CODE

uploaded = {}
total_bytes = 0
for p in pattern.split(','):
    for fp in glob.glob(p, recursive=True):
        path = Path(fp)
        if path.is_file():
            key = f'results/{path.name}'
            s3.upload_file(str(path), bucket, key)
            size = path.stat().st_size
            uploaded[key] = {'size': size}
            total_bytes += size
            print(f'  Uploaded: {path.name} ({size:,} bytes)')

# Upload final log
if Path('/workspace/stdout.log').exists():
    s3.upload_file('/workspace/stdout.log', bucket, 'logs/stdout.log')

# Signal done
s3.put_object(Bucket=bucket, Key='done.json', Body=json.dumps({
    'status': 'success' if exit_code == 0 else 'failed',
    'exit_code': exit_code, 'files': uploaded,
    'total_bytes': total_bytes, 'timestamp': time.time()
}))
print(f'[GPU2Vast] Done: exit_code={exit_code}, {len(uploaded)} files ({total_bytes:,} bytes)')
"
