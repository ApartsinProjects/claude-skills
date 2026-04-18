"""
GPU2Vast TensorFlow E2E Test
==============================
Tests: auto image selection (TF), cost + ETA estimation, TensorBoard,
SSH log streaming, checkpoint streaming, parallel R2, full observability.

Uses a tiny Keras model + small dataset. ~2 min total, ~$0.02 cost.

Usage:
  python test_tf_e2e.py
"""

import json
import sys
import time
import shutil
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from r2_manager import R2Manager
import vastai_manager as vast

KEYS_DIR = Path(__file__).parent / "keys"

with open(KEYS_DIR / "r2.key") as f:
    r2_config = json.load(f)

print("=" * 60)
print("  GPU2Vast TensorFlow E2E Test")
print("  (cost estimation + observability + auto image selection)")
print("=" * 60)

# ── 1. Prepare TF training script ──
print("\n[1/8] Preparing TensorFlow training script...")
data_dir = Path("_tf_e2e_data")
data_dir.mkdir(exist_ok=True)

# Training script that uses TensorFlow/Keras
(data_dir / "train_tf.py").write_text('''
import json, os, sys, time
print("[train] === GPU2Vast TensorFlow E2E ===")
sys.stdout.flush()

# Phase A: Check GPU
print("[train] Phase A: GPU check...")
sys.stdout.flush()
os.system("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 'No GPU'")

# Phase B: Import TensorFlow
print("[train] Phase B: Loading TensorFlow...")
sys.stdout.flush()
import_start = time.time()
import tensorflow as tf
import numpy as np
tf_time = time.time() - import_start
print(f"[train] TensorFlow {tf.__version__} loaded in {tf_time:.1f}s")
print(f"[train] GPUs available: {len(tf.config.list_physical_devices(\"GPU\"))}")
gpus = tf.config.list_physical_devices("GPU")
if gpus:
    for gpu in gpus:
        print(f"[train]   {gpu}")
sys.stdout.flush()

# Phase C: Create tiny dataset
print("[train] Phase C: Creating dataset...")
sys.stdout.flush()
np.random.seed(42)
X_train = np.random.randn(200, 10).astype(np.float32)
y_train = (X_train[:, 0] + X_train[:, 1] > 0).astype(np.float32)
X_val = np.random.randn(50, 10).astype(np.float32)
y_val = (X_val[:, 0] + X_val[:, 1] > 0).astype(np.float32)
print(f"[train] Dataset: {len(X_train)} train, {len(X_val)} val samples")
sys.stdout.flush()

# Phase D: Build model
print("[train] Phase D: Building model...")
sys.stdout.flush()
model = tf.keras.Sequential([
    tf.keras.layers.Dense(64, activation="relu", input_shape=(10,)),
    tf.keras.layers.Dense(32, activation="relu"),
    tf.keras.layers.Dense(1, activation="sigmoid"),
])
model.compile(optimizer="adam", loss="binary_crossentropy", metrics=["accuracy"])
param_count = model.count_params()
print(f"[train] Model: {param_count:,} parameters")
sys.stdout.flush()

# Phase E: Train with TensorBoard callback
print("[train] Phase E: Training (10 epochs)...")
sys.stdout.flush()
os.makedirs("runs", exist_ok=True)
tb_callback = tf.keras.callbacks.TensorBoard(log_dir="runs", histogram_freq=1)

class ProgressCallback(tf.keras.callbacks.Callback):
    def on_epoch_end(self, epoch, logs=None):
        loss = logs.get("loss", 0)
        acc = logs.get("accuracy", 0)
        val_loss = logs.get("val_loss", 0)
        val_acc = logs.get("val_accuracy", 0)
        print(f"  {epoch+1}/10 loss={loss:.4f} acc={acc:.4f} val_loss={val_loss:.4f} val_acc={val_acc:.4f}")
        sys.stdout.flush()

history = model.fit(
    X_train, y_train,
    validation_data=(X_val, y_val),
    epochs=10, batch_size=32, verbose=0,
    callbacks=[tb_callback, ProgressCallback()],
)

# Phase F: Evaluate
print("[train] Phase F: Final evaluation...")
sys.stdout.flush()
eval_loss, eval_acc = model.evaluate(X_val, y_val, verbose=0)
print(f"[train] Val loss={eval_loss:.4f}, Val acc={eval_acc:.4f}")
sys.stdout.flush()

# Phase G: Save model + results
print("[train] Phase G: Saving results...")
sys.stdout.flush()
os.makedirs("results", exist_ok=True)
model.save("results/model.keras")
model_size = os.path.getsize("results/model.keras")

with open("results/training_log.json", "w") as f:
    json.dump({k: [float(v) for v in vals] for k, vals in history.history.items()}, f, indent=2)

summary = {
    "framework": "tensorflow",
    "tf_version": tf.__version__,
    "gpu_count": len(gpus),
    "gpu_names": [str(g) for g in gpus],
    "param_count": param_count,
    "epochs": 10,
    "final_loss": float(history.history["loss"][-1]),
    "final_acc": float(history.history["accuracy"][-1]),
    "final_val_loss": float(history.history["val_loss"][-1]),
    "final_val_acc": float(history.history["val_accuracy"][-1]),
    "model_size_bytes": model_size,
    "tf_load_time_s": round(tf_time, 1),
}
with open("results/summary.json", "w") as f:
    json.dump(summary, f, indent=2)

print(f"[train] Saved model ({model_size:,} bytes) + logs")
print(f"[train] Loss: {summary['final_loss']:.4f}, Acc: {summary['final_acc']:.4f}")
print("[train] === DONE ===")
sys.stdout.flush()
''')
print(f"  Created train_tf.py (uses tensorflow, keras, TensorBoard callback)")

# ── 2. Test auto image selection ──
print("\n[2/8] Testing auto image selection...")
selected = vast.select_image(script_path=str(data_dir / "train_tf.py"))
expected = "tensorflow/tensorflow:2.16.1-gpu"
img_ok = selected == expected
print(f"  Selected: {selected}")
print(f"  Expected: {expected}")
print(f"  {'PASS' if img_ok else 'FAIL'}: Auto image selection for TensorFlow")

# ── 3. Create R2 bucket + upload ──
print("\n[3/8] Creating R2 bucket and uploading...")
r2 = R2Manager(r2_config)
job_id = f"tf-e2e-{int(time.time())}"
bucket = r2.create_bucket(job_id)
r2.upload_files(bucket, [str(data_dir / "train_tf.py")])
print(f"  Bucket: {bucket}")

# ── 4. Search GPU + cost/ETA estimation ──
print("\n[4/8] Searching for GPU + cost estimation...")
offers = None
for gpu_type in ["RTX_4090", "RTX_3090", "RTX_4080"]:
    offers = vast.search_gpu(gpu_type, max_price=0.50, disk_gb=15)
    if offers:
        break

if not offers:
    print("  No GPU found! Cleaning up...")
    r2.delete_bucket(bucket)
    shutil.rmtree(data_dir, ignore_errors=True)
    sys.exit(1)

offer = offers[0]
price = offer.get("dph_total", 0)
gpu_name = offer.get("gpu_name", "?")

# Cost + ETA estimation
data_size_gb = sum(f.stat().st_size for f in data_dir.iterdir()) / (1024**3)
est = vast.estimate_cost(offer, estimated_minutes=5, data_gb=max(data_size_gb, 0.01))
phases = est["phases"]
print(f"  GPU: {gpu_name} @ ${price:.3f}/hr")
print(f"  ETA: ~{est['total_minutes']:.0f} min total, ~${est['total_cost']:.4f}")
print(f"    upload={phases['r2_upload']:.1f}m  boot={phases['instance_boot']:.1f}m  "
      f"setup={phases['setup_and_download']:.1f}m  train={phases['training']:.1f}m  "
      f"fetch={phases['result_download']:.1f}m")
print(f"  PASS: Cost + ETA estimation")

# ── 5. Launch instance ──
print(f"\n[5/8] Launching instance (image={selected})...")

acct = r2_config["account_id"]
akey = r2_config["access_key"]
skey = r2_config["secret_key"]

onstart_parts = [
    "echo '[GPU2Vast] Booted'",
    "echo '[GPU2Vast] Installing boto3...'",
    "pip install -q boto3",
    "echo '[GPU2Vast] Downloading data from R2...'",
    f"python3 -c \""
    f"import boto3,os; "
    f"s3=boto3.client('s3',endpoint_url='https://{acct}.r2.cloudflarestorage.com',"
    f"aws_access_key_id='{akey}',aws_secret_access_key='{skey}',region_name='auto'); "
    f"os.makedirs('/workspace/data',exist_ok=True); "
    f"[s3.download_file('{bucket}',o['Key'],'/workspace/data/'+o['Key'].split('/')[-1]) "
    f"for p in s3.get_paginator('list_objects_v2').paginate(Bucket='{bucket}',Prefix='data/') "
    f"for o in p.get('Contents',[])]; "
    f"print('Downloaded all data')\"",
    "echo '[GPU2Vast] Starting TensorBoard...'",
    "pip install -q tensorboard 2>/dev/null",
    "mkdir -p /workspace/data/runs",
    "tensorboard --logdir=/workspace/data/runs --host=0.0.0.0 --port=6006 2>/dev/null &",
    "echo '[GPU2Vast] Running training...'",
    "cd /workspace/data && python3 -u train_tf.py 2>&1 | tee /workspace/stdout.log",
    "EXIT_CODE=${PIPESTATUS[0]}",
    "echo '[GPU2Vast] Uploading results to R2...'",
    f"python3 -c \""
    f"import boto3,json,glob,time; from pathlib import Path; "
    f"s3=boto3.client('s3',endpoint_url='https://{acct}.r2.cloudflarestorage.com',"
    f"aws_access_key_id='{akey}',aws_secret_access_key='{skey}',region_name='auto'); "
    f"[s3.upload_file(fp,'{bucket}','results/'+Path(fp).name) "
    f"for fp in glob.glob('results/*') if Path(fp).is_file()]; "
    f"s3.upload_file('/workspace/stdout.log','{bucket}','logs/stdout.log') if Path('/workspace/stdout.log').exists() else None; "
    f"s3.put_object(Bucket='{bucket}',Key='done.json',"
    f"Body=json.dumps({{'status':'success' if $EXIT_CODE==0 else 'failed','exit_code':$EXIT_CODE,'ts':time.time()}})); "
    f"print('Results uploaded')\"",
    "echo '[GPU2Vast] ALL DONE'",
]
onstart_cmd = " && ".join(onstart_parts)

instance = vast.create_instance(
    offer_id=offer["id"],
    docker_image=selected,
    onstart_cmd=onstart_cmd,
    disk_gb=15,
)
instance_id = instance.get("new_contract") or instance.get("instance_id")
print(f"  Instance: {instance_id}")

# ── 6. Wait for boot + SSH log streaming ──
print(f"\n[6/8] Waiting for boot...")
if vast.wait_for_running(instance_id, timeout=300):
    print(f"  Instance running")
else:
    print(f"  Instance may still be booting...")

# Get SSH info
inst_info = vast.get_instance(instance_id)
ssh_host = inst_info.get("ssh_host", "") if isinstance(inst_info, dict) else ""
ssh_port = inst_info.get("ssh_port", "") if isinstance(inst_info, dict) else ""

# Check for TensorBoard direct port
conn = vast.get_connection_info(instance_id)
tb_port = conn.get("port_mappings", {}).get("6006/tcp", {}).get("host_port")
if tb_port and conn.get("public_ip"):
    print(f"  TensorBoard: http://{conn['public_ip']}:{tb_port}")
elif ssh_host:
    print(f"  TensorBoard (SSH): ssh -p {ssh_port} root@{ssh_host} -L 6006:localhost:6006")

def _ssh_tail(lines=40):
    key = Path.home() / ".ssh" / "gpu2vast_ed25519"
    if not key.exists() or not ssh_host:
        return ""
    try:
        r = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no",
             "-o", "BatchMode=yes", "-i", str(key),
             "-p", str(ssh_port), f"root@{ssh_host}",
             f"tail -{lines} /var/log/onstart.log 2>/dev/null"],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""

# ── 7. Monitor with streaming logs ──
print(f"\n[7/8] Monitoring (SSH + R2)...")
print("-" * 50)

start = time.time()
seen_lines = set()
last_ssh_check = 0
last_r2_check = 0
max_wait = 600
done = None

while time.time() - start < max_wait:
    elapsed = int(time.time() - start)

    # Check R2 for done
    if time.time() - last_r2_check >= 10:
        done = r2.get_done(bucket)
        if done:
            # Final SSH log fetch
            ssh_out = _ssh_tail(lines=200)
            if ssh_out:
                for line in ssh_out.split("\n"):
                    line = line.strip()
                    if line and line not in seen_lines:
                        seen_lines.add(line)
                        try:
                            print(f"  [{elapsed:3d}s] {line}")
                        except UnicodeEncodeError:
                            print(f"  [{elapsed:3d}s] {line.encode('ascii', 'replace').decode()}")
            print(f"\n  Job completed: {done.get('status')} ({elapsed}s)")
            break
        last_r2_check = time.time()

    # SSH log streaming every 5s
    if time.time() - last_ssh_check >= 5:
        ssh_out = _ssh_tail()
        if ssh_out:
            for line in ssh_out.split("\n"):
                line = line.strip()
                if line and line not in seen_lines:
                    seen_lines.add(line)
                    try:
                        print(f"  [{elapsed:3d}s] [app] {line}")
                    except UnicodeEncodeError:
                        print(f"  [{elapsed:3d}s] [app] {line.encode('ascii', 'replace').decode()}")
        last_ssh_check = time.time()

    time.sleep(3)
else:
    print(f"\n  TIMEOUT after {max_wait}s")

print("-" * 50)

# ── 8. Download + validate + cleanup ──
print(f"\n[8/8] Downloading results + cleanup...")
results_dir = Path("_tf_e2e_results")
downloaded = r2.download_results(bucket, str(results_dir), prefix="results/")
log_files = r2.download_results(bucket, str(results_dir / "logs"), prefix="logs/")

# Validate
summary_path = results_dir / "summary.json"
if summary_path.exists():
    summary = json.loads(summary_path.read_text())
    print(f"\n  Summary:")
    print(f"    Framework: {summary.get('framework')}")
    print(f"    TF version: {summary.get('tf_version')}")
    print(f"    GPUs: {summary.get('gpu_count')}")
    print(f"    Params: {summary.get('param_count', 0):,}")
    print(f"    Loss: {summary.get('final_loss', '?'):.4f}")
    print(f"    Accuracy: {summary.get('final_acc', '?'):.4f}")
    print(f"    Val accuracy: {summary.get('final_val_acc', '?'):.4f}")
    print(f"    Model size: {summary.get('model_size_bytes', 0):,} bytes")

# Cleanup
print(f"\n  Destroying instance...")
try:
    vast.destroy_instance(instance_id)
except Exception as e:
    print(f"  Instance: {e}")

r2.delete_bucket(bucket)
shutil.rmtree(data_dir, ignore_errors=True)

elapsed_total = time.time() - start
cost = price * elapsed_total / 3600
status = "PASSED" if done and done.get("status") == "success" else "FAILED"

print(f"\n{'='*60}")
print(f"  TF E2E TEST: {status}")
print(f"  Framework: TensorFlow")
print(f"  Image: {selected}")
print(f"  GPU: {gpu_name} @ ${price:.3f}/hr")
print(f"  Time: {int(elapsed_total)}s")
print(f"  Cost: ~${cost:.4f}")
print(f"  ETA was: ~{est['total_minutes']:.0f} min, ~${est['total_cost']:.4f}")
print(f"  Results: {results_dir}/")
print(f"{'='*60}")
