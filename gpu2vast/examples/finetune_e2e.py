"""
GPU2Vast E2E Example: Fine-tune a small HuggingFace model on custom data.

Flow:
  1. Upload training data to R2
  2. Launch vast.ai instance
  3. Instance downloads data from R2 + fetches model from HuggingFace
  4. Train for a few steps
  5. Upload model weights + logs to R2
  6. Download weights + logs locally
  7. Cleanup (destroy instance, delete R2 bucket)

Usage:
  python examples/finetune_e2e.py
"""

import json
import sys
import time
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from r2_manager import R2Manager
import vastai_manager as vast

KEYS_DIR = Path(__file__).parent.parent / "keys"

with open(KEYS_DIR / "r2.key") as f:
    r2_config = json.load(f)

hf_token = ""
hf_key_path = KEYS_DIR / "huggingface.key"
if hf_key_path.exists():
    hf_token = hf_key_path.read_text().strip()

print("=" * 60)
print("  GPU2Vast E2E: Fine-tune HF model on custom data")
print("=" * 60)

# ── 1. Prepare training data ──
print("\n[1/8] Preparing training data...")
data_dir = Path("_e2e_finetune_data")
data_dir.mkdir(exist_ok=True)

train_samples = [
    {"text": f"The capital of France is Paris. Entity: France, Type: country"},
    {"text": f"Barack Obama was the 44th president. Entity: Barack Obama, Type: person"},
    {"text": f"Apple released the iPhone in 2007. Entity: Apple, Type: organization"},
    {"text": f"The Amazon River flows through Brazil. Entity: Amazon River, Type: location"},
    {"text": f"Tesla was founded by Elon Musk. Entity: Tesla, Type: organization"},
    {"text": f"Mount Everest is the tallest mountain. Entity: Mount Everest, Type: location"},
    {"text": f"Shakespeare wrote Hamlet in 1600. Entity: Shakespeare, Type: person"},
    {"text": f"Google acquired YouTube in 2006. Entity: Google, Type: organization"},
]
(data_dir / "train.json").write_text(json.dumps(train_samples, indent=2))
print(f"  Created {len(train_samples)} training samples")

# Training script that runs ON the vast.ai instance
(data_dir / "train.py").write_text('''
import json, os, sys, time
print("[train] Starting fine-tune E2E example")
sys.stdout.flush()

# Step 1: Check GPU
print("[train] Checking GPU...")
sys.stdout.flush()
os.system("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 'No GPU'")

# Step 2: Load model from HuggingFace
print("[train] Loading model from HuggingFace (distilbert-base-uncased)...")
sys.stdout.flush()
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

model_name = "distilbert-base-uncased"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=4)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = model.to(device)
print(f"[train] Model loaded on {device}")
sys.stdout.flush()

# Step 3: Load training data from R2 (already downloaded to /workspace/data/)
print("[train] Loading training data...")
sys.stdout.flush()
with open("train.json") as f:
    data = json.load(f)
print(f"[train] Loaded {len(data)} samples")
sys.stdout.flush()

label_map = {"country": 0, "person": 1, "organization": 2, "location": 3}
texts = [s["text"].split("Entity:")[0].strip() for s in data]
labels = [label_map.get(s["text"].split("Type:")[-1].strip(), 0) for s in data]

inputs = tokenizer(texts, padding=True, truncation=True, max_length=64, return_tensors="pt").to(device)
labels_tensor = torch.tensor(labels, device=device)

# Step 4: Train
print("[train] Training (20 steps)...")
sys.stdout.flush()
optimizer = torch.optim.AdamW(model.parameters(), lr=5e-5)
model.train()

log_entries = []
for step in range(1, 21):
    outputs = model(**inputs, labels=labels_tensor)
    loss = outputs.loss
    loss.backward()
    optimizer.step()
    optimizer.zero_grad()

    entry = {"step": step, "total": 20, "loss": f"{loss.item():.4f}"}
    log_entries.append(entry)
    print(f"  {step}/20 loss={loss.item():.4f}")
    sys.stdout.flush()
    time.sleep(0.5)

# Step 5: Save model weights + training log
print("[train] Saving model weights...")
sys.stdout.flush()
os.makedirs("results", exist_ok=True)
model.save_pretrained("results/model_weights")
tokenizer.save_pretrained("results/model_weights")

with open("results/training_log.json", "w") as f:
    json.dump(log_entries, f, indent=2)

with open("results/summary.json", "w") as f:
    json.dump({
        "model": model_name,
        "device": str(device),
        "samples": len(data),
        "steps": 20,
        "final_loss": log_entries[-1]["loss"],
    }, f, indent=2)

print(f"[train] Saved weights + logs to results/")
print("[train] DONE")
sys.stdout.flush()
''')
print(f"  Created train.py")

# ── 2. Create R2 bucket + upload ──
print("\n[2/8] Creating R2 bucket and uploading data...")
r2 = R2Manager(r2_config)
job_id = f"e2e-ft-{int(time.time())}"
bucket = r2.create_bucket(job_id)
r2.upload_files(bucket, [
    str(data_dir / "train.json"),
    str(data_dir / "train.py"),
])

# ── 3. Find GPU ──
print("\n[3/8] Searching for cheapest GPU...")
offers = None
for gpu_type in ["RTX_4090", "RTX_3090", "RTX_4080", "RTX_3080", "RTX_A4000"]:
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
gpu = offer.get("gpu_name", "?")
print(f"  Selected: {gpu} @ ${price:.3f}/hr")

# ── 4. Build onstart and launch ──
print("\n[4/8] Launching instance...")

acct = r2_config["account_id"]
akey = r2_config["access_key"]
skey = r2_config["secret_key"]

onstart_parts = [
    "echo '[GPU2Vast] Booted'",
    "echo '[GPU2Vast] Installing packages...'",
    "pip install -q boto3 transformers torch",
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
    f"Body=json.dumps({{'status':'success','ts':time.time()}})); "
    f"print('Results uploaded')\"",
    "echo '[GPU2Vast] ALL DONE'",
]
onstart_cmd = " && ".join(onstart_parts)

instance = vast.create_instance(
    offer_id=offer["id"],
    docker_image="vastai/pytorch",
    onstart_cmd=onstart_cmd,
    disk_gb=15,
)
instance_id = instance.get("new_contract") or instance.get("instance_id")
print(f"  Instance: {instance_id}")

# ── 5. Wait for boot ──
print("\n[5/8] Waiting for instance to boot...")
if vast.wait_for_running(instance_id, timeout=180):
    print(f"  Instance running")
else:
    print(f"  Instance may still be booting, continuing to monitor...")

# ── 6. Monitor with streaming logs ──
print("\n[6/8] Monitoring with streaming logs (15 min max)...")
print("-" * 50)

start = time.time()
seen_lines = set()
last_log_check = 0
max_wait = 900

while time.time() - start < max_wait:
    elapsed = int(time.time() - start)

    done = r2.get_done(bucket)
    if done:
        print(f"\n{'='*50}")
        print(f"  Job completed: {done.get('status')} ({elapsed}s)")
        break

    if time.time() - last_log_check >= 5:
        log_output = vast.get_logs(instance_id, tail=50)
        if log_output:
            for line in log_output.strip().split("\n"):
                line = line.strip()
                if line and line not in seen_lines:
                    seen_lines.add(line)
                    print(f"  [{elapsed:3d}s] {line}")
        last_log_check = time.time()

    time.sleep(3)
else:
    print(f"\n  Timeout after {max_wait}s")

# ── 7. Download results ──
print(f"\n[7/8] Downloading results (weights + logs)...")
results_dir = Path("_e2e_finetune_results")
downloaded = r2.download_results(bucket, str(results_dir), prefix="results/")
log_files = r2.download_results(bucket, str(results_dir / "logs"), prefix="logs/")
print(f"  Result files: {downloaded}")
print(f"  Log files: {log_files}")

for f in results_dir.rglob("*.json"):
    try:
        content = json.loads(f.read_text())
        if isinstance(content, dict):
            print(f"  {f.name}: {json.dumps(content, indent=2)[:200]}")
    except Exception:
        pass

# ── 8. Cleanup ──
print(f"\n[8/8] Cleaning up...")
try:
    vast.destroy_instance(instance_id)
except Exception as e:
    print(f"  Instance cleanup: {e}")

r2.delete_bucket(bucket)
shutil.rmtree(data_dir, ignore_errors=True)

cost = price * (time.time() - start) / 3600
status = "PASSED" if done and done.get("status") == "success" else "FAILED"
print(f"\n{'='*60}")
print(f"  E2E FINETUNE TEST: {status}")
print(f"  GPU: {gpu} @ ${price:.3f}/hr")
print(f"  Time: {int(time.time()-start)}s")
print(f"  Cost: ~${cost:.4f}")
print(f"  Results: {results_dir}/")
print(f"  Log lines captured: {len(seen_lines)}")
print(f"{'='*60}")
