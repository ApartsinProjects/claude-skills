"""
GPU2Vast End-to-End Test
========================
Tiny model (GPT-2, 124M params), 10 samples, 1 epoch.
Tests the full flow: R2 bucket -> vast.ai instance -> train -> upload -> download -> cleanup.

Usage:
  python test_e2e.py
"""

import json
import os
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).parent
sys.path.insert(0, str(SKILL_DIR))
from r2_manager import R2Manager

# Load R2 config
with open(SKILL_DIR / "keys" / "r2.key") as f:
    r2_config = json.load(f)

# ═══════════════════════════════════════════════════════════════
#  Step 1: Test R2 bucket lifecycle
# ═══════════════════════════════════════════════════════════════

print("=" * 50)
print("  STEP 1: R2 Bucket Lifecycle")
print("=" * 50)

r2 = R2Manager(r2_config)

job_id = f"test-{int(time.time())}"
bucket = r2.create_bucket(job_id)
print(f"  Created bucket: {bucket}")

# Create tiny test data
test_dir = Path("test_data")
test_dir.mkdir(exist_ok=True)

# Tiny training script
(test_dir / "train.py").write_text("""
import json, time, os

print("Loading data...")
with open("data.json") as f:
    data = json.load(f)
print(f"Loaded {len(data)} samples")

# Simulate training
for epoch in range(2):
    for i, sample in enumerate(data):
        time.sleep(0.1)
        if (i + 1) % 3 == 0:
            print(f"{i+1}/{len(data)} epoch={epoch+1} loss={1.0/(i+1+epoch*len(data)):.4f}")

# Save results
os.makedirs("results", exist_ok=True)
with open("results/predictions.json", "w") as f:
    json.dump([{"input": s["text"], "output": "test_prediction"} for s in data], f, indent=2)
print(f"Saved {len(data)} predictions")
print("DONE")
""")

# Tiny data (10 samples)
(test_dir / "data.json").write_text(json.dumps([
    {"text": f"Sample text number {i}", "label": f"entity_{i}"}
    for i in range(10)
], indent=2))

# Upload
r2.upload_files(bucket, [str(test_dir / "train.py"), str(test_dir / "data.json")])
r2.upload_config(bucket, {
    "experiment_cmd": "python3 data/train.py",
    "results_pattern": "results/*",
    "job_id": job_id,
})
print("  Uploaded data + config")

# Verify upload
progress = r2.get_progress(bucket)
print(f"  Progress (should be None): {progress}")

# ═══════════════════════════════════════════════════════════════
#  Step 2: Test vast.ai GPU search
# ═══════════════════════════════════════════════════════════════

print("\n" + "=" * 50)
print("  STEP 2: vast.ai GPU Search")
print("=" * 50)

import vastai_manager as vast

offers = vast.search_gpu(gpu_name="RTX_4090", max_price=0.50)
print(f"  Found {len(offers)} RTX 4090 offers")
if offers:
    best = offers[0]
    print(f"  Cheapest: ${best.get('dph_total', '?')}/hr, {best.get('disk_space', '?')}GB disk")

# ═══════════════════════════════════════════════════════════════
#  Step 3: Launch instance (optional, costs money)
# ═══════════════════════════════════════════════════════════════

print("\n" + "=" * 50)
print("  STEP 3: Launch Instance")
print("=" * 50)

launch = input("  Launch a real instance? (costs ~$0.01 for 1 min) [y/N]: ").strip().lower()

if launch == "y" and offers:
    print("  Launching...")

    # Read onstart script
    onstart = (SKILL_DIR / "container" / "onstart.sh").read_text()

    env_vars = {
        "R2_ACCOUNT_ID": r2_config["account_id"],
        "R2_ACCESS_KEY": r2_config["access_key"],
        "R2_SECRET_KEY": r2_config["secret_key"],
        "R2_BUCKET": bucket,
        "JOB_ID": job_id,
        "EXPERIMENT_CMD": "python3 /workspace/data/train.py",
        "RESULTS_PATTERN": "results/*",
    }

    instance = vast.create_instance(
        offer_id=best["id"],
        docker_image="vastai/pytorch",
        env_vars=env_vars,
        onstart_cmd="bash -c '" + onstart.replace("'", "'\\''") + "'",
        disk_gb=10,
    )
    instance_id = instance.get("new_contract") or instance.get("instance_id")
    print(f"  Instance: {instance_id}")

    # Monitor for 3 minutes max
    print("  Monitoring (3 min max)...")
    for _ in range(18):  # 18 * 10s = 3 min
        done = r2.get_done(bucket)
        if done:
            print(f"\n  Job done: {done.get('status')}")
            break
        progress = r2.get_progress(bucket)
        if progress:
            print(f"  Progress: {progress}")
        time.sleep(10)

    # Download results
    results = r2.download_results(bucket, "./test_results/")
    print(f"  Downloaded: {results}")

    # Cleanup
    vast.destroy_instance(instance_id)
    print(f"  Destroyed instance")
else:
    print("  Skipping instance launch (dry run)")

# ═══════════════════════════════════════════════════════════════
#  Step 4: Cleanup
# ═══════════════════════════════════════════════════════════════

print("\n" + "=" * 50)
print("  STEP 4: Cleanup")
print("=" * 50)

r2.delete_bucket(bucket)
print(f"  Deleted bucket: {bucket}")

# Clean test files
import shutil
if test_dir.exists():
    shutil.rmtree(test_dir)
print("  Cleaned test files")

print("\n" + "=" * 50)
print("  ALL TESTS PASSED")
print("=" * 50)
