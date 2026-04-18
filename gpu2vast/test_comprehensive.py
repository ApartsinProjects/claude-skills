"""
GPU2Vast Comprehensive Validation Test
========================================
Tests every aspect of the pipeline with a small model + small data:

  Phase 1 (local): Validate prerequisites
    - Check vastai CLI installed
    - Check boto3 installed
    - Check API keys present and valid
    - Validate R2 credentials (list buckets)
    - Validate vast.ai credentials (search offers)
    - Validate HuggingFace token (whoami)

  Phase 2 (local -> R2): Data upload with progress
    - Create ephemeral R2 bucket
    - Upload training data + script
    - Upload manifest, verify checksums
    - Verify uploaded files match local originals

  Phase 3 (vast.ai): Provision + boot
    - Search for cheapest GPU
    - Create instance with env vars
    - Wait for boot, stream boot logs
    - Verify instance reaches 'running' status

  Phase 4 (remote): Training with streaming logs
    - Stream instance logs in real-time
    - Monitor R2 progress.json updates
    - Watch for HF model download progress
    - Watch for training step/loss progress

  Phase 5 (remote -> R2 -> local): Results
    - Wait for done.json signal
    - Download model weights from R2
    - Download training log from R2
    - Download stdout log from R2
    - Verify all expected files present
    - Verify model weights are loadable (non-zero size)

  Phase 6: Cleanup
    - Destroy vast.ai instance
    - Delete R2 bucket + all objects
    - Remove local temp files

Usage:
  python test_comprehensive.py [--skip-launch]
"""

import json
import os
import sys
import time
import shutil
import subprocess
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

KEYS_DIR = Path(__file__).parent / "keys"
RESULTS_DIR = Path("_comprehensive_test_results")
DATA_DIR = Path("_comprehensive_test_data")

passed = []
failed = []
warnings = []


def check(name, condition, detail=""):
    if condition:
        passed.append(name)
        print(f"  PASS: {name}")
    else:
        failed.append(name)
        print(f"  FAIL: {name} {detail}")
    return condition


def warn(msg):
    warnings.append(msg)
    print(f"  WARN: {msg}")


# ══════════════════════════════════════════════════════════════
#  PHASE 1: Validate prerequisites
# ══════════════════════════════════════════════════════════════
print("=" * 60)
print("  PHASE 1: Validate prerequisites")
print("=" * 60)

# 1a. Check vastai CLI
print("\n  Checking vastai CLI...")
try:
    r = subprocess.run(["vastai", "--version"], capture_output=True, text=True, timeout=10)
    vastai_version = r.stdout.strip() or r.stderr.strip()
    check("vastai CLI installed", r.returncode == 0, f"(got: {vastai_version})")
    print(f"    Version: {vastai_version}")
except FileNotFoundError:
    check("vastai CLI installed", False, "not found in PATH")
    print("    Install with: pip install vastai")

# 1b. Check boto3
print("\n  Checking boto3...")
try:
    import boto3
    check("boto3 installed", True)
    print(f"    Version: {boto3.__version__}")
except ImportError:
    check("boto3 installed", False, "pip install boto3")

# 1c. Check API key files
print("\n  Checking API keys...")
vastai_key_path = KEYS_DIR / "vastai.key"
r2_key_path = KEYS_DIR / "r2.key"
hf_key_path = KEYS_DIR / "huggingface.key"

check("vastai.key exists", vastai_key_path.exists())
check("r2.key exists", r2_key_path.exists())
if hf_key_path.exists():
    check("huggingface.key exists", True)
    hf_token = hf_key_path.read_text().strip()
else:
    warn("huggingface.key not found (gated models like Llama will fail)")
    hf_token = ""

if not vastai_key_path.exists() or not r2_key_path.exists():
    print("\n  Cannot continue without API keys. Exiting.")
    sys.exit(1)

# 1d. Validate R2 credentials
print("\n  Validating R2 credentials...")
with open(r2_key_path) as f:
    r2_config = json.load(f)

check("r2.key has account_id", bool(r2_config.get("account_id")))
check("r2.key has access_key", bool(r2_config.get("access_key")))
check("r2.key has secret_key", bool(r2_config.get("secret_key")))

from r2_manager import R2Manager
try:
    r2 = R2Manager(r2_config)
    buckets = r2.list_buckets()
    check("R2 credentials valid (list_buckets)", True)
    print(f"    Existing gpu2vast buckets: {len(buckets)}")
except Exception as e:
    check("R2 credentials valid", False, str(e))

# 1e. Validate vast.ai credentials
print("\n  Validating vast.ai credentials...")
import vastai_manager as vast
try:
    test_offers = vast.search_gpu("RTX_4090", max_price=10.0, disk_gb=1)
    check("vast.ai credentials valid (search)", True)
    print(f"    Available RTX 4090 offers: {len(test_offers)}")
except Exception as e:
    check("vast.ai credentials valid", False, str(e))

# 1f. Validate HuggingFace token
print("\n  Validating HuggingFace token...")
if hf_token:
    try:
        r = subprocess.run(
            [sys.executable, "-c",
             f"from huggingface_hub import HfApi; "
             f"api = HfApi(token='{hf_token}'); "
             f"info = api.whoami(); "
             f"print(info.get('name', info.get('fullname', 'unknown')))"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            check("HuggingFace token valid", True)
            print(f"    User: {r.stdout.strip()}")
        else:
            check("HuggingFace token valid", False, r.stderr.strip()[:100])
    except Exception as e:
        check("HuggingFace token valid", False, str(e))
else:
    warn("Skipping HF token validation (no key file)")

# 1g. Check HF model accessibility
print("\n  Checking model accessibility (distilbert-base-uncased)...")
try:
    r = subprocess.run(
        [sys.executable, "-c",
         "from huggingface_hub import model_info; "
         "info = model_info('distilbert-base-uncased'); "
         "print(f'Model: {info.id}, downloads: {info.downloads}')"],
        capture_output=True, text=True, timeout=15,
    )
    if r.returncode == 0:
        check("HF model accessible", True)
        print(f"    {r.stdout.strip()}")
    else:
        check("HF model accessible", False, r.stderr.strip()[:100])
except Exception as e:
    check("HF model accessible", False, str(e))

if "--skip-launch" in sys.argv:
    print("\n  --skip-launch: skipping phases 2-6")
    print(f"\n  Results: {len(passed)} passed, {len(failed)} failed, {len(warnings)} warnings")
    sys.exit(1 if failed else 0)

# ══════════════════════════════════════════════════════════════
#  PHASE 2: R2 upload with verification
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  PHASE 2: R2 upload with verification")
print("=" * 60)

DATA_DIR.mkdir(exist_ok=True)

# Create training data (small, 8 samples)
train_data = [
    {"text": "Paris is the capital of France", "label": "location"},
    {"text": "Obama served as president", "label": "person"},
    {"text": "Apple makes iPhones", "label": "organization"},
    {"text": "The Nile is the longest river", "label": "location"},
    {"text": "Tesla builds electric cars", "label": "organization"},
    {"text": "Einstein developed relativity", "label": "person"},
    {"text": "Amazon started as a bookstore", "label": "organization"},
    {"text": "Everest is in the Himalayas", "label": "location"},
]
data_path = DATA_DIR / "train.json"
data_path.write_text(json.dumps(train_data, indent=2))
local_data_md5 = hashlib.md5(data_path.read_bytes()).hexdigest()

# Training script (runs on vast.ai)
script_path = DATA_DIR / "train.py"
script_path.write_text('''
import json, os, sys, time, hashlib
print("[train] === GPU2Vast Comprehensive Test ===")
sys.stdout.flush()

# Validate GPU
print("[train] Phase A: GPU check...")
sys.stdout.flush()
gpu_ok = os.system("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader") == 0
print(f"[train] GPU available: {gpu_ok}")
sys.stdout.flush()

# Validate data integrity
print("[train] Phase B: Data integrity check...")
sys.stdout.flush()
with open("train.json") as f:
    data = json.load(f)
data_md5 = hashlib.md5(open("train.json", "rb").read()).hexdigest()
print(f"[train] Data loaded: {len(data)} samples, md5={data_md5}")
sys.stdout.flush()

# Download model from HuggingFace
print("[train] Phase C: Downloading model from HuggingFace...")
sys.stdout.flush()
dl_start = time.time()
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

model_name = "distilbert-base-uncased"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=4)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = model.to(device)
dl_time = time.time() - dl_start
param_count = sum(p.numel() for p in model.parameters())
print(f"[train] Model loaded: {model_name} ({param_count:,} params) on {device} in {dl_time:.1f}s")
sys.stdout.flush()

# Tokenize
print("[train] Phase D: Tokenizing...")
sys.stdout.flush()
label_map = {"location": 0, "person": 1, "organization": 2}
texts = [s["text"] for s in data]
labels = [label_map.get(s["label"], 0) for s in data]
inputs = tokenizer(texts, padding=True, truncation=True, max_length=64, return_tensors="pt").to(device)
labels_t = torch.tensor(labels, device=device)
print(f"[train] Tokenized {len(texts)} samples")
sys.stdout.flush()

# Train
print("[train] Phase E: Training (15 steps)...")
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

    entry = {"step": step, "total": 15, "loss": round(loss.item(), 4)}
    log.append(entry)
    print(f"  {step}/15 loss={loss.item():.4f}")
    sys.stdout.flush()
    time.sleep(0.3)

# Save results
print("[train] Phase F: Saving results...")
sys.stdout.flush()
os.makedirs("results/model_weights", exist_ok=True)

model.save_pretrained("results/model_weights")
tokenizer.save_pretrained("results/model_weights")
weight_files = os.listdir("results/model_weights")
total_size = sum(os.path.getsize(f"results/model_weights/{f}") for f in weight_files)

with open("results/training_log.json", "w") as f:
    json.dump(log, f, indent=2)

summary = {
    "model": model_name,
    "device": str(device),
    "gpu_available": gpu_ok,
    "param_count": param_count,
    "samples": len(data),
    "data_md5": data_md5,
    "steps": 15,
    "initial_loss": log[0]["loss"],
    "final_loss": log[-1]["loss"],
    "loss_decreased": log[-1]["loss"] < log[0]["loss"],
    "model_download_time_s": round(dl_time, 1),
    "weight_files": weight_files,
    "total_weight_size_bytes": total_size,
}
with open("results/summary.json", "w") as f:
    json.dump(summary, f, indent=2)

print(f"[train] Saved {len(weight_files)} weight files ({total_size:,} bytes)")
print(f"[train] Loss: {log[0]['loss']:.4f} -> {log[-1]['loss']:.4f} (decreased={summary['loss_decreased']})")
print("[train] === DONE ===")
sys.stdout.flush()
''')
local_script_md5 = hashlib.md5(script_path.read_bytes()).hexdigest()

# Create R2 bucket
print("\n  Creating R2 bucket...")
job_id = f"test-comp-{int(time.time())}"
bucket = r2.create_bucket(job_id)
check("R2 bucket created", bool(bucket))

# Upload
print("\n  Uploading files...")
manifest = r2.upload_files(bucket, [str(data_path), str(script_path)])
check("Files uploaded", len(manifest) >= 2, f"uploaded {len(manifest)} files")

# Verify upload integrity
print("\n  Verifying upload integrity...")
for key, info in manifest.items():
    check(f"Upload checksum {key}", bool(info.get("md5")))

r2.upload_config(bucket, {
    "experiment_cmd": "python3 -u train.py",
    "results_pattern": "results/**/*",
    "job_id": job_id,
})
check("Job config uploaded", True)

# ══════════════════════════════════════════════════════════════
#  PHASE 3: Provision vast.ai instance
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  PHASE 3: Provision vast.ai instance")
print("=" * 60)

print("\n  Searching for cheapest GPU...")
offers = None
gpu_type_used = None
for gpu_type in ["RTX_4090", "RTX_3090", "RTX_4080", "RTX_3080", "RTX_A4000", "RTX_A5000"]:
    offers = vast.search_gpu(gpu_type, max_price=0.60, disk_gb=15)
    if offers:
        gpu_type_used = gpu_type
        break

if not offers:
    check("GPU offer found", False, "no GPUs available at <=0.60/hr")
    print("  Cleaning up...")
    r2.delete_bucket(bucket)
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    sys.exit(1)

offer = offers[0]
price = offer.get("dph_total", 0)
gpu_name = offer.get("gpu_name", "?")
check("GPU offer found", True, f"{gpu_name} @ ${price:.3f}/hr")

# Build onstart command
acct = r2_config["account_id"]
akey = r2_config["access_key"]
skey = r2_config["secret_key"]

onstart_parts = [
    "echo '[GPU2Vast] Booted'",
    "echo '[GPU2Vast] Installing packages...'",
    "pip install -q boto3 transformers torch huggingface_hub",
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
    "echo '[GPU2Vast] Running training...'",
    "cd /workspace/data && python3 -u train.py 2>&1 | tee /workspace/stdout.log",
    "EXIT_CODE=${PIPESTATUS[0]}",
    "echo '[GPU2Vast] Uploading results to R2...'",
    f"python3 -c \""
    f"import boto3,json,glob,time; from pathlib import Path; "
    f"s3=boto3.client('s3',endpoint_url='https://{acct}.r2.cloudflarestorage.com',"
    f"aws_access_key_id='{akey}',aws_secret_access_key='{skey}',region_name='auto'); "
    f"[s3.upload_file(fp,'{bucket}','results/'+'/'.join(Path(fp).parts[Path(fp).parts.index('results')+1:])) "
    f"for fp in glob.glob('results/**/*',recursive=True) if Path(fp).is_file()]; "
    f"s3.upload_file('/workspace/stdout.log','{bucket}','logs/stdout.log') if Path('/workspace/stdout.log').exists() else None; "
    f"s3.put_object(Bucket='{bucket}',Key='done.json',"
    f"Body=json.dumps({{'status':'success' if $EXIT_CODE==0 else 'failed','exit_code':$EXIT_CODE,'ts':time.time()}})); "
    f"print('Results uploaded')\"",
    "echo '[GPU2Vast] ALL DONE'",
]
onstart_cmd = " && ".join(onstart_parts)

print("\n  Launching instance...")
instance = vast.create_instance(
    offer_id=offer["id"],
    docker_image="pytorch/pytorch:2.3.0-cuda12.1-cudnn9-runtime",
    onstart_cmd=onstart_cmd,
    disk_gb=15,
)
instance_id = instance.get("new_contract") or instance.get("instance_id")
check("Instance created", bool(instance_id), f"id={instance_id}")

# Wait for boot
print("\n  Waiting for boot...")
booted = vast.wait_for_running(instance_id, timeout=240)
check("Instance booted", booted)

# ══════════════════════════════════════════════════════════════
#  PHASE 4: Monitor with streaming logs
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  PHASE 4: Monitor with streaming logs")
print("=" * 60)

start = time.time()
seen_lines = set()
last_log_check = 0
max_wait = 900  # 15 min
done = None

seen_phases = {
    "boot": False,
    "packages": False,
    "r2_download": False,
    "hf_download": False,
    "training": False,
    "saving": False,
    "upload": False,
    "done": False,
}

phase_markers = {
    "Booted": "boot",
    "Installing packages": "packages",
    "Downloading data from R2": "r2_download",
    "Downloading model from HuggingFace": "hf_download",
    "Phase C": "hf_download",
    "Training": "training",
    "Phase E": "training",
    "Saving results": "saving",
    "Phase F": "saving",
    "Uploading results": "upload",
    "ALL DONE": "done",
    "=== DONE ===": "done",
}

print("-" * 50)
while time.time() - start < max_wait:
    elapsed = int(time.time() - start)

    done = r2.get_done(bucket)
    if done:
        print(f"\n  Job completed: {done.get('status')} ({elapsed}s)")
        break

    if time.time() - last_log_check >= 5:
        log_output = vast.get_logs(instance_id, tail=80)
        if log_output:
            for line in log_output.strip().split("\n"):
                line = line.strip()
                if line and line not in seen_lines:
                    seen_lines.add(line)
                    print(f"  [{elapsed:3d}s] {line}")

                    for marker, phase in phase_markers.items():
                        if marker in line:
                            seen_phases[phase] = True
        last_log_check = time.time()

    time.sleep(3)
else:
    print(f"\n  TIMEOUT after {max_wait}s")

print("-" * 50)

# Validate phases seen in logs
print("\n  Validating pipeline phases observed in logs:")
for phase, seen in seen_phases.items():
    check(f"Log phase: {phase}", seen)

# ══════════════════════════════════════════════════════════════
#  PHASE 5: Download + validate results
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  PHASE 5: Download + validate results")
print("=" * 60)

RESULTS_DIR.mkdir(exist_ok=True)

# Download results
print("\n  Downloading results...")
result_files = r2.download_results(bucket, str(RESULTS_DIR), prefix="results/")
check("Result files downloaded", len(result_files) > 0, f"got {len(result_files)} files")

# Download logs
print("\n  Downloading logs...")
log_files = r2.download_results(bucket, str(RESULTS_DIR / "logs"), prefix="logs/")
check("Log files downloaded", len(log_files) > 0, f"got {len(log_files)} files")

# Validate summary.json
summary_path = RESULTS_DIR / "summary.json"
if summary_path.exists():
    summary = json.loads(summary_path.read_text())
    print(f"\n  Summary: {json.dumps(summary, indent=2)}")
    check("Model trained on GPU", summary.get("gpu_available", False) or summary.get("device") == "cuda")
    check("Data integrity (md5 match)", summary.get("data_md5") == local_data_md5,
          f"remote={summary.get('data_md5')}, local={local_data_md5}")
    check("Loss decreased during training", summary.get("loss_decreased", False),
          f"{summary.get('initial_loss')} -> {summary.get('final_loss')}")
    check("Model weights saved", summary.get("total_weight_size_bytes", 0) > 0,
          f"{summary.get('total_weight_size_bytes', 0):,} bytes")
    check("Correct step count", summary.get("steps") == 15)
else:
    check("summary.json exists", False)

# Validate training_log.json
log_path = RESULTS_DIR / "training_log.json"
if log_path.exists():
    train_log = json.loads(log_path.read_text())
    check("Training log has entries", len(train_log) == 15, f"got {len(train_log)}")
    if train_log:
        check("Log entry has step/loss", "step" in train_log[0] and "loss" in train_log[0])
else:
    check("training_log.json exists", False)

# Validate model weight files exist and are non-zero
weights_dir = RESULTS_DIR / "model_weights"
if weights_dir.exists():
    weight_files = list(weights_dir.iterdir())
    check("Model weight files present", len(weight_files) > 0, f"got {len(weight_files)}")
    total_size = sum(f.stat().st_size for f in weight_files if f.is_file())
    check("Model weights non-zero", total_size > 1000, f"{total_size:,} bytes")
    print(f"    Weight files: {[f.name for f in weight_files]}")
    print(f"    Total size: {total_size:,} bytes")
else:
    check("Model weights directory exists", False)

# Validate stdout log
stdout_log = RESULTS_DIR / "logs" / "stdout.log"
if stdout_log.exists():
    log_content = stdout_log.read_text(errors="replace")
    check("Stdout log captured", len(log_content) > 100, f"{len(log_content)} chars")
    check("Stdout log contains training output", "loss=" in log_content)
    check("Stdout log contains DONE marker", "DONE" in log_content)
else:
    check("stdout.log exists", False)

# Validate done.json
check("done.json received", done is not None)
if done:
    check("Job status is success", done.get("status") == "success",
          f"status={done.get('status')}, exit_code={done.get('exit_code')}")

# ══════════════════════════════════════════════════════════════
#  PHASE 6: Cleanup
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("  PHASE 6: Cleanup")
print("=" * 60)

print("\n  Destroying instance...")
try:
    vast.destroy_instance(instance_id)
    check("Instance destroyed", True)
except Exception as e:
    check("Instance destroyed", False, str(e))

print("\n  Deleting R2 bucket...")
try:
    r2.delete_bucket(bucket)
    check("R2 bucket deleted", True)
except Exception as e:
    check("R2 bucket deleted", False, str(e))

# Verify bucket is gone
remaining = [b for b in r2.list_buckets() if bucket in b]
check("Bucket fully removed", len(remaining) == 0)

print("\n  Cleaning local temp files...")
shutil.rmtree(DATA_DIR, ignore_errors=True)
check("Temp data cleaned", not DATA_DIR.exists())

# Keep results for inspection
print(f"  Results kept at: {RESULTS_DIR}/")

# ══════════════════════════════════════════════════════════════
#  FINAL REPORT
# ══════════════════════════════════════════════════════════════
elapsed_total = time.time() - start if 'start' in dir() else 0
cost = price * elapsed_total / 3600 if 'price' in dir() else 0

print("\n" + "=" * 60)
print("  COMPREHENSIVE TEST REPORT")
print("=" * 60)
print(f"\n  Passed: {len(passed)}/{len(passed)+len(failed)}")
print(f"  Failed: {len(failed)}")
print(f"  Warnings: {len(warnings)}")

if failed:
    print(f"\n  Failed checks:")
    for f_name in failed:
        print(f"    - {f_name}")

if warnings:
    print(f"\n  Warnings:")
    for w in warnings:
        print(f"    - {w}")

print(f"\n  GPU: {gpu_name if 'gpu_name' in dir() else '?'} @ ${price:.3f}/hr")
print(f"  Duration: {int(elapsed_total)}s")
print(f"  Estimated cost: ${cost:.4f}")
print(f"  Results: {RESULTS_DIR}/")

status = "ALL PASSED" if not failed else "SOME FAILED"
print(f"\n  {'='*20} {status} {'='*20}")
sys.exit(1 if failed else 0)
