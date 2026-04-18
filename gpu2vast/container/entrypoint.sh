#!/bin/bash
# GPU2Vast Container Entrypoint
# Downloads data from R2, runs experiment, uploads results, signals done

set -e

echo "[GPU2Vast] Starting job: $JOB_ID"
echo "[GPU2Vast] Bucket: $R2_BUCKET"
echo "[GPU2Vast] Command: $EXPERIMENT_CMD"

# 1. Download experiment data from R2
echo "[GPU2Vast] Downloading data from R2..."
pip install -q boto3 > /dev/null 2>&1
python /gpu2vast/r2_download.py

# 2. Install extra requirements
if [ -f /workspace/data/requirements.txt ]; then
    echo "[GPU2Vast] Installing extra requirements..."
    pip install -q -r /workspace/data/requirements.txt
fi

# 3. Start progress reporter in background
python /gpu2vast/progress_reporter.py &
REPORTER_PID=$!

# 4. Run the experiment
echo "[GPU2Vast] Running experiment..."
cd /workspace/data
eval "$EXPERIMENT_CMD" 2>&1 | tee /workspace/stdout.log
EXIT_CODE=${PIPESTATUS[0]}

# 5. Stop progress reporter
kill $REPORTER_PID 2>/dev/null || true

# 6. Upload results + logs to R2
echo "[GPU2Vast] Uploading results..."
python /gpu2vast/r2_upload.py --exit-code $EXIT_CODE

echo "[GPU2Vast] Done (exit code: $EXIT_CODE)"
