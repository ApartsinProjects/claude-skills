"""GPU2Vast Full E2E Test: launches a real vast.ai instance with live log streaming."""
import sys
import json
import time
import os
import shutil
import subprocess
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from r2_manager import R2Manager
import vastai_manager as vast

KEYS_DIR = Path(__file__).parent / "keys"
VAST_KEY = (KEYS_DIR / "vastai.key").read_text().strip()

with open(KEYS_DIR / "r2.key") as f:
    r2_config = json.load(f)

print("=" * 60)
print("  GPU2Vast FULL E2E TEST (with live logs)")
print("=" * 60)

# ── 1. Create R2 bucket ──
print("\n[1/8] Creating R2 bucket...")
r2 = R2Manager(r2_config)
job_id = f"e2e-{int(time.time())}"
bucket = r2.create_bucket(job_id)
print(f"  ✓ Bucket: {bucket}")

# ── 2. Upload test script ──
print("\n[2/8] Uploading test data...")
test_dir = Path("_e2e_test")
test_dir.mkdir(exist_ok=True)

# The script that runs ON vast.ai
(test_dir / "train.py").write_text("""
import json, time, os, sys

print("[STEP 1] Checking GPU...")
sys.stdout.flush()
os.system("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 'No GPU detected'")

print("[STEP 2] Simulating training (20 steps)...")
sys.stdout.flush()
for step in range(1, 21):
    time.sleep(0.5)
    loss = 1.0 / step
    print(f"  {step}/20 loss={loss:.4f} epoch=1")
    sys.stdout.flush()

print("[STEP 3] Saving results...")
sys.stdout.flush()
os.makedirs("results", exist_ok=True)
with open("results/predictions.json", "w") as f:
    json.dump({"test": "passed", "steps": 20, "final_loss": 0.05}, f, indent=2)

print("[DONE] Training complete!")
sys.stdout.flush()
""")

r2.upload_files(bucket, [str(test_dir / "train.py")])
print(f"  ✓ Uploaded train.py")

# ── 3. Find cheapest GPU ──
print("\n[3/8] Searching for cheapest GPU...")
offers = None
for gpu_type in ["RTX_4090", "RTX_3090", "RTX_4080", "RTX_3080", "RTX_A4000"]:
    offers = vast.search_gpu(gpu_type, max_price=0.40, disk_gb=10)
    if offers:
        break

if not offers:
    print("  ✗ No GPU found! Cleaning up...")
    r2.delete_bucket(bucket)
    shutil.rmtree(test_dir, ignore_errors=True)
    sys.exit(1)

offer = offers[0]
price = offer.get("dph_total", 0)
gpu = offer.get("gpu_name", "?")
print(f"  ✓ {gpu} @ ${price:.3f}/hr (id={offer['id']})")

# ── 4. Build onstart command ──
print("\n[4/8] Launching instance...")

acct = r2_config["account_id"]
akey = r2_config["access_key"]
skey = r2_config["secret_key"]

# The onstart script: download from R2 → run → upload to R2
# Each step prints progress to stdout (visible via vastai logs)
onstart_parts = [
    "echo '[GPU2Vast] Booted successfully'",
    "echo '[GPU2Vast] Installing boto3...'",
    "pip install -q boto3",
    "echo '[GPU2Vast] Downloading data from R2...'",
    f"python3 -c \"import boto3; s3=boto3.client('s3',endpoint_url='https://{acct}.r2.cloudflarestorage.com',aws_access_key_id='{akey}',aws_secret_access_key='{skey}',region_name='auto'); "
    f"import os; os.makedirs('/workspace/data',exist_ok=True); "
    f"[s3.download_file('{bucket}',o['Key'],'/workspace/data/'+o['Key'].split('/')[-1]) "
    f"for p in s3.get_paginator('list_objects_v2').paginate(Bucket='{bucket}',Prefix='data/') "
    f"for o in p.get('Contents',[])]; print('Downloaded all data')\"",
    "echo '[GPU2Vast] Running experiment...'",
    "cd /workspace/data && python3 -u train.py",
    "echo '[GPU2Vast] Uploading results...'",
    f"python3 -c \"import boto3,json,glob,time; from pathlib import Path; "
    f"s3=boto3.client('s3',endpoint_url='https://{acct}.r2.cloudflarestorage.com',aws_access_key_id='{akey}',aws_secret_access_key='{skey}',region_name='auto'); "
    f"[s3.upload_file(fp,'{bucket}','results/'+Path(fp).name) for fp in glob.glob('results/*')]; "
    f"s3.put_object(Bucket='{bucket}',Key='done.json',Body=json.dumps({{'status':'success','ts':time.time()}})); "
    f"print('Results uploaded to R2')\"",
    "echo '[GPU2Vast] ALL DONE'",
]
onstart_cmd = " && ".join(onstart_parts)

instance = vast.create_instance(
    offer_id=offer["id"],
    docker_image="pytorch/pytorch:2.3.0-cuda12.1-cudnn9-runtime",
    onstart_cmd=onstart_cmd,
    disk_gb=10,
)
instance_id = instance.get("new_contract") or instance.get("instance_id")
print(f"  ✓ Instance: {instance_id}")

# ── 5. Wait for instance to boot ──
print("\n[5/8] Waiting for instance to boot...")
if vast.wait_for_running(instance_id, timeout=180):
    print(f"  ✓ Instance running")
else:
    print(f"  ⚠ Instance may still be booting")

# ── 6. Stream logs (main monitoring loop) ──
print("\n[6/8] Streaming instance logs (10 min max)...")
print("-" * 50)

start = time.time()
seen_lines = set()
last_log_check = 0
max_wait = 600  # 10 minutes

while time.time() - start < max_wait:
    elapsed = int(time.time() - start)

    # Check R2 for done signal (fast check every 10s)
    done = r2.get_done(bucket)
    if done:
        print(f"\n{'='*50}")
        print(f"  ✓ Job completed: {done.get('status')} ({elapsed}s)")
        break

    # Stream logs every 5 seconds
    if time.time() - last_log_check >= 5:
        try:
            result = subprocess.run(
                ["vastai", "--api-key", VAST_KEY, "logs", str(instance_id), "--tail", "50"],
                capture_output=True, text=True, timeout=10,
            )
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if line and line not in seen_lines:
                        seen_lines.add(line)
                        print(f"  [{elapsed:3d}s] {line}")
        except Exception:
            pass
        last_log_check = time.time()

    time.sleep(2)
else:
    print(f"\n  ⚠ Timeout after {max_wait}s")

# ── 7. Download results ──
print(f"\n[7/8] Downloading results...")
downloaded = r2.download_results(bucket, "_e2e_results/")
print(f"  Files: {downloaded}")

for f in downloaded:
    if f.endswith(".json"):
        with open(f) as fh:
            print(f"  {Path(f).name}: {json.load(fh)}")

# ── 8. Cleanup ──
print(f"\n[8/8] Cleaning up...")
try:
    vast.destroy_instance(instance_id)
    print(f"  ✓ Destroyed instance {instance_id}")
except Exception as e:
    print(f"  Instance: {e}")

r2.delete_bucket(bucket)
print(f"  ✓ Deleted bucket {bucket}")

shutil.rmtree(test_dir, ignore_errors=True)
shutil.rmtree("_e2e_results", ignore_errors=True)

cost = price * (time.time() - start) / 3600
status = "PASSED" if done and done.get("status") == "success" else "FAILED"
print(f"\n{'='*60}")
print(f"  E2E TEST {status}")
print(f"  GPU: {gpu} @ ${price:.3f}/hr")
print(f"  Time: {int(time.time()-start)}s")
print(f"  Cost: ${cost:.4f}")
print(f"  Log lines captured: {len(seen_lines)}")
print(f"{'='*60}")
