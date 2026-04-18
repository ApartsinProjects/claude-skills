#!/bin/bash
# GPU2Vast On-Start Script for vast.ai instances
# Runs automatically when instance boots. Uses vast.ai pre-cached base image.
set -e

echo "[GPU2Vast] Starting job: $JOB_ID"

# 1. Install Python packages (using uv if available, else pip)
echo "[GPU2Vast] Installing packages..."
if command -v uv &> /dev/null; then
    uv pip install --system boto3 transformers accelerate peft trl \
        bitsandbytes sentence-transformers datasets requests
else
    pip install --no-cache-dir boto3 transformers accelerate peft trl \
        bitsandbytes sentence-transformers datasets requests
fi

# 2. Download experiment data from R2
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
for page in paginator.paginate(Bucket=bucket, Prefix='data/'):
    for obj in page.get('Contents', []):
        key = obj['Key']
        local = ws / key.replace('data/', '', 1)
        local.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(bucket, key, str(local))
        print(f'  Downloaded: {key} ({obj[\"Size\"]:,} bytes)')
"

# 3. Install extra requirements if present
if [ -f /workspace/data/requirements.txt ]; then
    echo "[GPU2Vast] Installing extra requirements..."
    pip install -q -r /workspace/data/requirements.txt
fi

# 4. Start progress reporter in background
python3 -c "
import boto3, json, os, re, time, subprocess
from pathlib import Path

s3 = boto3.client('s3',
    endpoint_url=f'https://{os.environ[\"R2_ACCOUNT_ID\"]}.r2.cloudflarestorage.com',
    aws_access_key_id=os.environ['R2_ACCESS_KEY'],
    aws_secret_access_key=os.environ['R2_SECRET_KEY'],
    region_name='auto')
bucket = os.environ['R2_BUCKET']

while True:
    try:
        log = Path('/workspace/stdout.log')
        progress = {}
        if log.exists():
            for line in reversed(log.read_text(errors='replace').split('\n')[-100:]):
                for key, pat in [('step', r'(\d+)/(\d+)'), ('loss', r'loss[=: ]+([0-9.]+)'), ('epoch', r'epoch[=: ]+([0-9.]+)')]:
                    if key not in progress:
                        m = re.search(pat, line, re.I)
                        if m:
                            progress[key] = m.group(1)
                            if key == 'step' and m.lastindex >= 2: progress['total'] = m.group(2)
        progress['timestamp'] = time.time()
        progress['job_id'] = os.environ.get('JOB_ID', '')
        try:
            r = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5)
            parts = r.stdout.strip().split(', ')
            progress['gpu_util'] = int(parts[0])
            progress['gpu_mem'] = int(parts[1])
        except: pass
        s3.put_object(Bucket=bucket, Key='progress.json', Body=json.dumps(progress))
    except: pass
    time.sleep(30)
" &

# 5. Run experiment
echo "[GPU2Vast] Running: $EXPERIMENT_CMD"
cd /workspace/data
eval "$EXPERIMENT_CMD" 2>&1 | tee /workspace/stdout.log
EXIT_CODE=${PIPESTATUS[0]}

# 6. Upload results to R2
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
for p in pattern.split(','):
    for fp in glob.glob(p, recursive=True):
        path = Path(fp)
        if path.is_file():
            key = f'results/{path.name}'
            s3.upload_file(str(path), bucket, key)
            uploaded[key] = {'size': path.stat().st_size}
            print(f'  Uploaded: {path.name}')

# Upload log
if Path('/workspace/stdout.log').exists():
    s3.upload_file('/workspace/stdout.log', bucket, 'logs/stdout.log')

# Signal done
s3.put_object(Bucket=bucket, Key='done.json', Body=json.dumps({
    'status': 'success' if exit_code == 0 else 'failed',
    'exit_code': exit_code, 'files': uploaded, 'timestamp': time.time()
}))
print(f'[GPU2Vast] Done: exit_code={exit_code}')
"
