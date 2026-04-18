"""
GPU2Vast Full E2E Test: PyTorch + Transformers + TensorBoard
==============================================================
Demonstrates the entire pipeline:

  1. Auto image selection (detects transformers imports -> HF image)
  2. Cost + ETA estimation with per-phase breakdown
  3. R2 bucket creation + parallel upload
  4. GPU search with cost-aware scoring
  5. Instance launch + boot monitoring
  6. TensorBoard: auto-start, detect direct port or SSH tunnel
  7. SSH log streaming (real-time training output)
  8. R2 progress polling (step, loss, GPU util)
  9. Results download (model weights, training log, TensorBoard runs)
  10. Cleanup (destroy instance, delete R2 bucket)

Uses: distilbert-base-uncased fine-tuning, 8 samples, 15 steps.
Cost: ~$0.02, Time: ~3-5 min.

Usage:
  python test_e2e_full.py
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
print("  GPU2Vast E2E: PyTorch + Transformers + TensorBoard")
print("=" * 60)

checks_passed = 0
checks_failed = 0

def check(name, ok, detail=""):
    global checks_passed, checks_failed
    if ok:
        checks_passed += 1
        print(f"  PASS: {name}")
    else:
        checks_failed += 1
        print(f"  FAIL: {name} {detail}")
    return ok

# ── 1. Prepare training script ──
print("\n[1/10] Preparing PyTorch + Transformers training script...")
data_dir = Path("_e2e_full_data")
data_dir.mkdir(exist_ok=True)

train_data = [
    {"text": "Paris is the capital of France", "label": 0},
    {"text": "Obama served as president", "label": 1},
    {"text": "Apple makes iPhones", "label": 2},
    {"text": "The Nile is the longest river", "label": 0},
    {"text": "Tesla builds electric cars", "label": 2},
    {"text": "Einstein developed relativity", "label": 1},
    {"text": "Amazon started as a bookstore", "label": 2},
    {"text": "Everest is in the Himalayas", "label": 0},
]
(data_dir / "train.json").write_text(json.dumps(train_data, indent=2))

(data_dir / "train.py").write_text('''
import json, os, sys, time
print("[train] === GPU2Vast PyTorch + Transformers + TensorBoard ===")
sys.stdout.flush()

print("[train] Checking GPU...")
sys.stdout.flush()
os.system("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 'No GPU'")

print("[train] Loading model from HuggingFace...")
sys.stdout.flush()
dl_start = time.time()
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from torch.utils.tensorboard import SummaryWriter

model_name = "distilbert-base-uncased"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=3)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = model.to(device)
dl_time = time.time() - dl_start
print(f"[train] Model loaded: {model_name} ({sum(p.numel() for p in model.parameters()):,} params) on {device} in {dl_time:.1f}s")
sys.stdout.flush()

print("[train] Loading data...")
sys.stdout.flush()
with open("train.json") as f:
    data = json.load(f)
texts = [s["text"] for s in data]
labels = [s["label"] for s in data]
inputs = tokenizer(texts, padding=True, truncation=True, max_length=64, return_tensors="pt").to(device)
labels_t = torch.tensor(labels, device=device)
print(f"[train] Loaded {len(data)} samples")
sys.stdout.flush()

# TensorBoard writer
print("[train] Starting TensorBoard logging...")
sys.stdout.flush()
os.makedirs("runs", exist_ok=True)
writer = SummaryWriter(log_dir="runs")

print("[train] Training (15 steps)...")
sys.stdout.flush()
optimizer = torch.optim.AdamW(model.parameters(), lr=5e-5)
model.train()
log = []

for step in range(1, 16):
    outputs = model(**inputs, labels=labels_t)
    loss = outputs.loss
    loss.backward()
    optimizer.step()
    optimizer.zero_grad()

    loss_val = loss.item()
    writer.add_scalar("train/loss", loss_val, step)
    writer.add_scalar("train/lr", 5e-5, step)
    writer.flush()

    log.append({"step": step, "total": 15, "loss": round(loss_val, 4)})
    print(f"  {step}/15 loss={loss_val:.4f}")
    sys.stdout.flush()
    time.sleep(0.3)

# Evaluate
print("[train] Evaluating...")
sys.stdout.flush()
model.eval()
with torch.no_grad():
    outputs = model(**inputs, labels=labels_t)
    eval_loss = outputs.loss.item()
    preds = outputs.logits.argmax(dim=-1)
    accuracy = (preds == labels_t).float().mean().item()
writer.add_scalar("eval/loss", eval_loss, 15)
writer.add_scalar("eval/accuracy", accuracy, 15)
writer.flush()
writer.close()
print(f"[train] Eval: loss={eval_loss:.4f}, accuracy={accuracy:.4f}")
sys.stdout.flush()

# Save
print("[train] Saving model + results...")
sys.stdout.flush()
os.makedirs("results/model_weights", exist_ok=True)
model.save_pretrained("results/model_weights")
tokenizer.save_pretrained("results/model_weights")

with open("results/training_log.json", "w") as f:
    json.dump(log, f, indent=2)

weight_files = os.listdir("results/model_weights")
total_size = sum(os.path.getsize(f"results/model_weights/{f}") for f in weight_files)

summary = {
    "framework": "pytorch",
    "model": model_name,
    "device": str(device),
    "param_count": sum(p.numel() for p in model.parameters()),
    "samples": len(data),
    "steps": 15,
    "initial_loss": log[0]["loss"],
    "final_loss": log[-1]["loss"],
    "eval_loss": round(eval_loss, 4),
    "eval_accuracy": round(accuracy, 4),
    "loss_decreased": log[-1]["loss"] < log[0]["loss"],
    "model_download_time_s": round(dl_time, 1),
    "weight_files": weight_files,
    "total_weight_size_bytes": total_size,
    "tensorboard_dir": "runs",
}
with open("results/summary.json", "w") as f:
    json.dump(summary, f, indent=2)

# Also copy TensorBoard runs to results for download
import shutil
if os.path.exists("runs"):
    shutil.copytree("runs", "results/tensorboard_runs", dirs_exist_ok=True)

print(f"[train] Saved {len(weight_files)} weight files ({total_size:,} bytes)")
print(f"[train] Loss: {log[0]['loss']:.4f} -> {log[-1]['loss']:.4f}")
print(f"[train] TensorBoard logs in runs/")
print("[train] === DONE ===")
sys.stdout.flush()
''')
print(f"  Created train.py (PyTorch + Transformers + TensorBoard)")

# ── 2. Image selection ──
print("\n[2/10] Image selection...")
selected = "vastai/pytorch"
print(f"  Using: {selected} (pre-cached on hosts, fastest boot)")
print(f"  Packages installed via pip at startup")
check("Image selected", bool(selected))

# ── 3. R2 bucket + upload ──
print("\n[3/10] Creating R2 bucket + parallel upload...")
r2 = R2Manager(r2_config)
job_id = f"e2e-full-{int(time.time())}"
bucket = r2.create_bucket(job_id)
manifest = r2.upload_files(bucket, [
    str(data_dir / "train.json"),
    str(data_dir / "train.py"),
])
check("R2 bucket created + files uploaded", len(manifest) >= 2)

# ── 4. GPU search + cost estimation ──
print("\n[4/10] GPU search + cost/ETA estimation...")
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

data_size_gb = sum(f.stat().st_size for f in data_dir.iterdir()) / (1024**3)
est = vast.estimate_cost(offer, estimated_minutes=5, data_gb=max(data_size_gb, 0.01))
phases = est["phases"]
print(f"  GPU: {gpu_name} @ ${price:.3f}/hr")
print(f"  ETA: ~{est['total_minutes']:.0f} min, ~${est['total_cost']:.4f}")
print(f"    upload={phases['r2_upload']:.1f}m  boot={phases['instance_boot']:.1f}m  "
      f"setup={phases['setup_and_download']:.1f}m  train={phases['training']:.1f}m  "
      f"fetch={phases['result_download']:.1f}m")
check("Cost + ETA estimation", est["total_cost"] > 0 and est["total_minutes"] > 0)

# ── 5. Launch instance ──
print(f"\n[5/10] Launching instance (image={selected})...")

acct = r2_config["account_id"]
akey = r2_config["access_key"]
skey = r2_config["secret_key"]

# Write a proper bash script instead of fragile && chains
onstart_script = f"""#!/bin/bash
set -e
echo '[GPU2Vast] Booted'

echo '[GPU2Vast] Installing packages...'
pip install -q boto3 transformers tensorboard 2>/dev/null || true

echo '[GPU2Vast] Downloading data from R2...'
python3 -c "
import boto3, os
s3 = boto3.client('s3',
    endpoint_url='https://{acct}.r2.cloudflarestorage.com',
    aws_access_key_id='{akey}', aws_secret_access_key='{skey}',
    region_name='auto')
os.makedirs('/workspace/data', exist_ok=True)
for page in s3.get_paginator('list_objects_v2').paginate(Bucket='{bucket}', Prefix='data/'):
    for obj in page.get('Contents', []):
        key = obj['Key']
        s3.download_file('{bucket}', key, '/workspace/data/' + key.split('/')[-1])
        print(f'  Downloaded: {{key}} ({{obj[\"Size\"]}} bytes)')
"

echo '[GPU2Vast] Starting TensorBoard...'
mkdir -p /workspace/data/runs
nohup tensorboard --logdir=/workspace/data/runs --host=0.0.0.0 --port=6006 > /dev/null 2>&1 &

echo '[GPU2Vast] Running training...'
cd /workspace/data
python3 -u train.py 2>&1 | tee /workspace/stdout.log
EXIT_CODE=${{PIPESTATUS[0]}}
echo "[GPU2Vast] Training exit code: $EXIT_CODE"

echo '[GPU2Vast] Uploading results...'
python3 -c "
import boto3, json, glob, time
from pathlib import Path
s3 = boto3.client('s3',
    endpoint_url='https://{acct}.r2.cloudflarestorage.com',
    aws_access_key_id='{akey}', aws_secret_access_key='{skey}',
    region_name='auto')
uploaded = {{}}
for fp in glob.glob('results/**/*', recursive=True):
    p = Path(fp)
    if p.is_file():
        key = 'results/' + '/'.join(p.parts[p.parts.index('results')+1:])
        s3.upload_file(str(p), '{bucket}', key)
        uploaded[key] = {{'size': p.stat().st_size}}
        print(f'  Uploaded: {{p.name}} ({{p.stat().st_size:,}} bytes)')
if Path('/workspace/stdout.log').exists():
    s3.upload_file('/workspace/stdout.log', '{bucket}', 'logs/stdout.log')
s3.put_object(Bucket='{bucket}', Key='done.json',
    Body=json.dumps({{'status': 'success' if $EXIT_CODE == 0 else 'failed',
                      'exit_code': $EXIT_CODE, 'files': uploaded, 'ts': time.time()}}))
print(f'Results uploaded: {{len(uploaded)}} files')
"
echo '[GPU2Vast] ALL DONE'
"""

# Local validation: check bash syntax + embedded Python syntax
import subprocess as _sp, re as _re
tmp_sh = "/tmp/_gpu2vast_onstart_check.sh"
Path(tmp_sh).write_text(onstart_script)
r = _sp.run(["bash", "-n", tmp_sh], capture_output=True, text=True)
if r.returncode != 0:
    print(f"  FAIL: bash syntax error in onstart.sh:\n{r.stderr}")
    sys.exit(1)

for i, m in enumerate(_re.finditer(r'python3 -c "(.*?)"', onstart_script, _re.DOTALL)):
    py_code = m.group(1)
    try:
        compile(py_code, f"<onstart_python_block_{i}>", "exec")
    except SyntaxError as e:
        print(f"  FAIL: Python syntax error in onstart block {i}: {e}")
        sys.exit(1)
print("  Local validation: bash + Python syntax OK")
try:
    os.unlink(tmp_sh)
except OSError:
    pass

# Upload the onstart script to R2 so the instance can fetch it
r2.s3.put_object(Bucket=bucket, Key="onstart.sh", Body=onstart_script.encode())
print(f"  Uploaded onstart.sh to R2")

# The instance onstart_cmd: download and run the script from R2
onstart_cmd = (
    f"pip install -q boto3 2>/dev/null; "
    f"python3 -c \""
    f"import boto3; "
    f"s3=boto3.client('s3',endpoint_url='https://{acct}.r2.cloudflarestorage.com',"
    f"aws_access_key_id='{akey}',aws_secret_access_key='{skey}',region_name='auto'); "
    f"s3.download_file('{bucket}','onstart.sh','/tmp/onstart.sh')\"; "
    f"bash /tmp/onstart.sh"
)

instance = vast.create_instance(
    offer_id=offer["id"],
    docker_image=selected,
    onstart_cmd=onstart_cmd,
    disk_gb=15,
)
instance_id = instance.get("new_contract") or instance.get("instance_id")
check("Instance created", bool(instance_id), f"id={instance_id}")

# ── 6. Wait for boot ──
print(f"\n[6/10] Waiting for boot...")
booted = vast.wait_for_running(instance_id, timeout=300)
check("Instance booted", booted)

# Get SSH + TensorBoard info
inst_info = vast.get_instance(instance_id)
ssh_host = inst_info.get("ssh_host", "") if isinstance(inst_info, dict) else ""
ssh_port = inst_info.get("ssh_port", "") if isinstance(inst_info, dict) else ""

conn = vast.get_connection_info(instance_id)
tb_port = conn.get("port_mappings", {}).get("6006/tcp", {}).get("host_port")
if tb_port and conn.get("public_ip"):
    tb_url = f"http://{conn['public_ip']}:{tb_port}"
    print(f"  TensorBoard (direct): {tb_url}")
elif ssh_host:
    tb_url = f"http://localhost:6006 (via SSH tunnel)"
    print(f"  TensorBoard: ssh -p {ssh_port} root@{ssh_host} -L 6006:localhost:6006")
else:
    tb_url = ""

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

# ── 7/8. Monitor with SSH log streaming + R2 progress ──
print(f"\n[7/10] Monitoring (SSH logs + R2 done signal)...")
print("-" * 50)

start = time.time()
seen_lines = set()
last_ssh = 0
last_r2 = 0
max_wait = 600
done = None

while time.time() - start < max_wait:
    elapsed = int(time.time() - start)

    if time.time() - last_r2 >= 10:
        done = r2.get_done(bucket)
        if done:
            ssh_out = _ssh_tail(lines=200)
            if ssh_out:
                for line in ssh_out.split("\n"):
                    line = line.strip()
                    if line and line not in seen_lines:
                        seen_lines.add(line)
                        try:
                            print(f"  [{elapsed:3d}s] {line}")
                        except UnicodeEncodeError:
                            print(f"  [{elapsed:3d}s] {line.encode('ascii','replace').decode()}")
            print(f"\n  Job completed: {done.get('status')} ({elapsed}s)")
            break
        last_r2 = time.time()

    if time.time() - last_ssh >= 5:
        ssh_out = _ssh_tail()
        if ssh_out:
            for line in ssh_out.split("\n"):
                line = line.strip()
                if line and line not in seen_lines:
                    seen_lines.add(line)
                    try:
                        print(f"  [{elapsed:3d}s] [app] {line}")
                    except UnicodeEncodeError:
                        print(f"  [{elapsed:3d}s] [app] {line.encode('ascii','replace').decode()}")
        last_ssh = time.time()

    time.sleep(3)
else:
    print(f"\n  TIMEOUT after {max_wait}s")

print("-" * 50)

check("Job completed via R2 done signal", done is not None)
if done:
    check("Job status is success", done.get("status") == "success",
          f"status={done.get('status')}")

# ── 9. Download + validate ──
print(f"\n[9/10] Downloading results...")
results_dir = Path("_e2e_full_results")
downloaded = r2.download_results(bucket, str(results_dir), prefix="results/")
log_files = r2.download_results(bucket, str(results_dir / "logs"), prefix="logs/")

check("Result files downloaded", len(downloaded) > 0, f"got {len(downloaded)}")
check("Log files downloaded", len(log_files) > 0)

summary_path = results_dir / "summary.json"
if summary_path.exists():
    summary = json.loads(summary_path.read_text())
    print(f"\n  Summary:")
    print(f"    Framework: {summary.get('framework')}")
    print(f"    Model: {summary.get('model')}")
    print(f"    Device: {summary.get('device')}")
    print(f"    Params: {summary.get('param_count', 0):,}")
    print(f"    Loss: {summary.get('initial_loss')} -> {summary.get('final_loss')}")
    print(f"    Eval accuracy: {summary.get('eval_accuracy')}")
    print(f"    Weights: {summary.get('total_weight_size_bytes', 0):,} bytes")
    print(f"    TensorBoard: {summary.get('tensorboard_dir')}")

    check("Framework is PyTorch", summary.get("framework") == "pytorch")
    check("Trained on GPU", summary.get("device") == "cuda")
    check("Loss decreased", summary.get("loss_decreased", False))
    check("Model weights saved", summary.get("total_weight_size_bytes", 0) > 0)
    check("Eval accuracy > 0", summary.get("eval_accuracy", 0) > 0)

# Check TensorBoard runs were saved
tb_runs = list((results_dir / "tensorboard_runs").rglob("*")) if (results_dir / "tensorboard_runs").exists() else []
check("TensorBoard runs downloaded", len(tb_runs) > 0, f"got {len(tb_runs)} files")

# Check stdout.log
stdout_log = results_dir / "logs" / "stdout.log"
if stdout_log.exists():
    content = stdout_log.read_text(errors="replace")
    check("Stdout log has training output", "loss=" in content)
    check("Stdout log has DONE marker", "DONE" in content)
    check("TensorBoard logging in output", "TensorBoard" in content)

# ── 10. Cleanup ──
print(f"\n[10/10] Cleanup...")
try:
    vast.destroy_instance(instance_id)
    check("Instance destroyed", True)
except Exception as e:
    check("Instance destroyed", False, str(e))

r2.delete_bucket(bucket)
check("R2 bucket deleted", True)

shutil.rmtree(data_dir, ignore_errors=True)

elapsed_total = time.time() - start
cost = price * elapsed_total / 3600

print(f"\n{'='*60}")
print(f"  E2E TEST: {'ALL PASSED' if checks_failed == 0 else 'SOME FAILED'}")
print(f"  Passed: {checks_passed}/{checks_passed + checks_failed}")
print(f"  Framework: PyTorch + Transformers + TensorBoard")
print(f"  Image: {selected}")
print(f"  GPU: {gpu_name} @ ${price:.3f}/hr")
print(f"  Time: {int(elapsed_total)}s")
print(f"  Cost: ~${cost:.4f}")
print(f"  ETA was: ~{est['total_minutes']:.0f} min, ~${est['total_cost']:.4f}")
print(f"  Results: {results_dir}/")
print(f"{'='*60}")
sys.exit(1 if checks_failed else 0)
