"""
GPU2RunPod Smoke Test — covers all features and flows.

Phases:
  0  Preflight      — packages, key files, config loading
  1  Storage        — connect, upload, download, verify, delete
  2  RunPod API     — auth, list GPU types, find target GPU, pricing
  3  SSH keys       — generate / verify key pair
  4  End-to-end job — create pod, boot, SSH, bootstrap, progress reporter,
                      GPU observer, TensorBoard, training, results, cleanup

Usage:
  python smoke_test.py                    # full test (phases 0-4)
  python smoke_test.py --phases 0,1,2,3  # skip end-to-end pod (cheaper)
  python smoke_test.py --gpu RTX_3090    # override GPU type
  python smoke_test.py --keep-pod        # don't terminate pod on success
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SKILL_DIR = Path(__file__).parent
sys.path.insert(0, str(SKILL_DIR))

# ─── Result tracking ─────────────────────────────────────────────────────────

_results: list[tuple[bool, str]] = []
_phase_results: dict[int, list] = {}
_current_phase = 0


def check(ok: bool, label: str, detail: str = "") -> bool:
    sym = "PASS" if ok else "FAIL"
    suffix = f"  ({detail})" if detail else ""
    print(f"    [{sym}] {label}{suffix}")
    _results.append((ok, label))
    _phase_results.setdefault(_current_phase, []).append((ok, label))
    return ok


def phase(n: int, title: str):
    global _current_phase
    _current_phase = n
    print(f"\n{'='*60}")
    print(f"  Phase {n}: {title}")
    print(f"{'='*60}")


def summary():
    total = len(_results)
    passed = sum(1 for ok, _ in _results if ok)
    failed = total - passed
    print(f"\n{'='*60}")
    print(f"  SMOKE TEST SUMMARY: {passed}/{total} checks passed")
    for ph, checks in sorted(_phase_results.items()):
        ph_pass = sum(1 for ok, _ in checks if ok)
        ph_sym = "PASS" if ph_pass == len(checks) else "FAIL"
        print(f"  Phase {ph}: [{ph_sym}] {ph_pass}/{len(checks)}")
    if failed:
        print(f"\n  FAILED checks:")
        for ok, label in _results:
            if not ok:
                print(f"    [FAIL] {label}")
    print(f"{'='*60}")
    return failed == 0


# ─── Minimal smoke training script (embedded, written to temp file) ──────────

SMOKE_TRAIN = '''\
import sys, time, os, shutil
import torch
from torch.utils.tensorboard import SummaryWriter

assert torch.cuda.is_available(), "CUDA not available"
device = torch.device("cuda")
print(f"[train] GPU: {torch.cuda.get_device_name(0)}"); sys.stdout.flush()

writer = SummaryWriter(log_dir="runs")
writer.add_text("phase", "smoke_start", 0); writer.flush()

# Trivial CUDA op
x = torch.randn(512, 512, device=device)
_ = x @ x.T
print("[train] CUDA matmul: OK"); sys.stdout.flush()

writer.add_text("phase", "training_start", 0)
print("[train] Training (5 steps)..."); sys.stdout.flush()
for step in range(1, 6):
    time.sleep(1)
    loss = 1.0 / step
    print(f"  {step}/5 loss={loss:.4f} epoch=1"); sys.stdout.flush()
    writer.add_scalar("train/loss", loss, step)

writer.add_scalar("eval/loss", 0.20, 5)
writer.add_scalar("eval/accuracy", 0.95, 5)
writer.add_text("phase", "done", 5)
writer.close()

os.makedirs("results", exist_ok=True)
shutil.copytree("runs", "results/tb_runs", dirs_exist_ok=True)

gpu_name = torch.cuda.get_device_name(0)
vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
with open("results/smoke_result.txt", "w") as f:
    f.write(f"GPU: {gpu_name}\\n")
    f.write(f"VRAM_GB: {vram_gb:.1f}\\n")
    f.write(f"CUDA: {torch.version.cuda}\\n")
    f.write(f"loss_final: 0.2000\\n")
    f.write("STATUS: PASS\\n")

print("[train] Eval: loss=0.2000, accuracy=0.9500"); sys.stdout.flush()
print("[train] Loss: 1.0000 -> 0.2000"); sys.stdout.flush()
print("[train] === DONE ==="); sys.stdout.flush()
'''


# ─── Phase 0: Preflight ──────────────────────────────────────────────────────

def phase0_preflight():
    phase(0, "Preflight — packages, key files, config")

    for pkg in ["runpod", "boto3", "yaml", "botocore"]:
        try:
            __import__(pkg)
            check(True, f"Package: {pkg}")
        except ImportError as e:
            check(False, f"Package: {pkg}", str(e))

    keys_dir = SKILL_DIR / "keys"
    for fname in ["runpod.key", "runpod_storage.key"]:
        path = keys_dir / fname
        check(path.exists(), f"Key file: {fname}", str(path))

    try:
        from runpod_runner import load_config
        cfg = load_config()
        check(bool(cfg.get("runpod", {}).get("api_key")), "Config: runpod.api_key loaded")
        sc = cfg.get("storage", {})
        check(bool(sc.get("volume_id")), "Config: storage.volume_id loaded")
        check(bool(sc.get("access_key")), "Config: storage.access_key loaded")
        check(bool(sc.get("endpoint")), "Config: storage.endpoint loaded",
              sc.get("endpoint", "MISSING"))
        return cfg
    except Exception as e:
        check(False, "Config loading", str(e))
        return {}


# ─── Phase 1: Storage ────────────────────────────────────────────────────────

def phase1_storage(cfg: dict):
    phase(1, "Storage — connect, upload, download, verify, delete")

    if not cfg.get("storage"):
        check(False, "Storage config present")
        return False

    from runpod_storage import RunPodStorage

    try:
        st = RunPodStorage(cfg["storage"])
        check(True, "RunPodStorage instantiated")
    except Exception as e:
        check(False, "RunPodStorage instantiated", str(e))
        return False

    job_id = f"smoke-test-{int(time.time())}"

    try:
        st.create_bucket(job_id)
        check(True, "Volume accessible (create_bucket)")
    except Exception as e:
        check(False, "Volume accessible (create_bucket)", str(e))
        return False

    # Upload a small test file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("gpu2runpod smoke test payload\n")
        tmp_path = f.name

    try:
        st.upload_files(job_id, [tmp_path], prefix="data/")
        check(True, "Upload test file")
    except Exception as e:
        check(False, "Upload test file", str(e))

    # Upload config
    try:
        st.upload_config(job_id, {"smoke": True, "timestamp": time.time()})
        check(True, "Upload config (job_config.json)")
    except Exception as e:
        check(False, "Upload config", str(e))

    # Verify uploads via head_object (list_objects_v2 broken on RunPod S3 — always returns empty)
    try:
        check_keys = [
            f"{job_id}/data/{Path(tmp_path).name}",
            f"{job_id}/job_config.json",
        ]
        found = []
        for key in check_keys:
            try:
                st.s3.head_object(Bucket=st.volume_id, Key=key)
                found.append(Path(key).name)
            except Exception:
                pass
        check(len(found) >= 2, f"Uploaded objects accessible ({len(found)} via head_object)",
              ", ".join(found) if found else "none")
    except Exception as e:
        check(False, "Verify uploads", str(e))

    # Download results (simulate by uploading a done.json)
    result_key = f"{job_id}/results/test_result.txt"
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("STATUS: PASS\n")
            result_tmp = f.name
        st.s3.upload_file(result_tmp, st.volume_id, result_key)
        os.unlink(result_tmp)
        check(True, "Upload simulated result file")
    except Exception as e:
        check(False, "Upload simulated result file", str(e))

    try:
        with tempfile.TemporaryDirectory() as dl_dir:
            # Pass explicit key — list_objects_v2 broken on RunPod S3
            downloaded = st.download_results(job_id, dl_dir, manifest_keys=[result_key])
            check(len(downloaded) > 0, f"Download results ({len(downloaded)} files)")
            result_file = Path(dl_dir) / "test_result.txt"
            if result_file.exists():
                content = result_file.read_text()
                check("STATUS: PASS" in content, "Downloaded content correct")
    except Exception as e:
        check(False, "Download results", str(e))

    # Test progress/done/error sentinel methods
    try:
        st.s3.put_object(
            Bucket=st.volume_id,
            Key=f"{job_id}/progress.json",
            Body=json.dumps({"phase": "training", "loss": "0.42", "step": "3", "total": "5"}),
        )
        progress = st.get_progress(job_id)
        check(progress is not None and progress.get("phase") == "training",
              "get_progress() reads progress.json")
    except Exception as e:
        check(False, "get_progress()", str(e))

    try:
        st.s3.put_object(
            Bucket=st.volume_id,
            Key=f"{job_id}/done.json",
            Body=json.dumps({"status": "success", "exit_code": 0}),
        )
        done = st.get_done(job_id)
        check(done is not None and done.get("status") == "success",
              "get_done() reads done.json")
    except Exception as e:
        check(False, "get_done()", str(e))

    # Cleanup — verify via head_object (listing unreliable on RunPod S3)
    try:
        st.delete_job(job_id)
        # Spot-check: both known keys should return 404 after delete
        still_present = []
        for key in [f"{job_id}/data/{Path(tmp_path).name}", f"{job_id}/job_config.json"]:
            try:
                st.s3.head_object(Bucket=st.volume_id, Key=key)
                still_present.append(Path(key).name)
            except Exception:
                pass
        check(len(still_present) == 0, "delete_job() removes objects",
              f"still present: {still_present}" if still_present else "all gone")
    except Exception as e:
        check(False, "delete_job()", str(e))

    os.unlink(tmp_path)
    return True


# ─── Phase 2: RunPod API ─────────────────────────────────────────────────────

def phase2_runpod_api(cfg: dict, target_gpu: str = "RTX_4090"):
    phase(2, f"RunPod API — auth, GPU list, pricing for {target_gpu}")

    try:
        import runpod_manager as rp
        check(True, "Import runpod_manager")
    except Exception as e:
        check(False, "Import runpod_manager", str(e))
        return None

    try:
        rp._init()
        check(True, "RunPod API authentication")
    except Exception as e:
        check(False, "RunPod API authentication", str(e))
        return None

    try:
        gpus = rp.get_gpu_types()
        check(isinstance(gpus, list) and len(gpus) > 0, f"List GPU types ({len(gpus)} found)")
        community = [g for g in gpus if g.get("communityCloud")]
        secure = [g for g in gpus if g.get("secureCloud")]
        # INFO only — availability flags may be absent from GPU type metadata
        print(f"    [INFO] Community Cloud GPU types: {len(community)}")
        print(f"    [INFO] Secure Cloud GPU types: {len(secure)}")
    except Exception as e:
        check(False, "List GPU types", str(e))

    try:
        gpu_info = rp.search_gpu(target_gpu, max_price=None, cloud_type="COMMUNITY")
        if gpu_info:
            price = gpu_info.get("_resolved_price", "?")
            mem = gpu_info.get("memoryInGb", "?")
            check(True, f"Find {target_gpu} in Community Cloud", f"~${price:.2f}/hr, {mem}GB VRAM")
        else:
            check(False, f"Find {target_gpu} in Community Cloud",
                  "not available — try RTX_3090 or A100")
        return gpu_info
    except Exception as e:
        check(False, f"Find {target_gpu}", str(e))
        return None


# ─── Phase 3: SSH keys ───────────────────────────────────────────────────────

def phase3_ssh_keys():
    phase(3, "SSH keys — generate / verify")

    ssh_key = SKILL_DIR / "keys" / "ssh" / "gpu2runpod_ed25519"
    ssh_pub = Path(str(ssh_key) + ".pub")

    if not ssh_key.exists():
        try:
            result = subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-f", str(ssh_key), "-N", "", "-C", "gpu2runpod"],
                capture_output=True, check=True,
            )
            check(True, "Generate ED25519 key pair")
        except Exception as e:
            check(False, "Generate ED25519 key pair", str(e))
            return False
    else:
        check(True, "ED25519 private key exists", str(ssh_key))

    check(ssh_pub.exists(), "Public key exists", str(ssh_pub))
    if ssh_pub.exists():
        pub_content = ssh_pub.read_text().strip()
        check(pub_content.startswith("ssh-ed25519"), "Public key format valid")
        print(f"    [INFO] Public key: {pub_content[:60]}...")

    return True


# ─── Phase 4: End-to-end job ─────────────────────────────────────────────────

def phase4_e2e(cfg: dict, gpu_type: str = "RTX_3090", keep_pod: bool = False):
    phase(4, f"End-to-end job — full pipeline on {gpu_type}")

    import runpod_manager as rp
    from runpod_storage import RunPodStorage

    storage = RunPodStorage(cfg["storage"])
    job_id = f"smoke-e2e-{int(time.time())}"
    pod_id = None
    ssh_host = None
    ssh_port = None

    print(f"    [INFO] Job ID: {job_id}")
    required_keys: dict = {}

    try:
        # Write smoke training script to temp file
        smoke_script = SKILL_DIR / "jobs" / "smoke_train.py"
        smoke_script.write_text(SMOKE_TRAIN)
        check(True, "Write smoke training script", str(smoke_script))

        # Upload scripts to storage
        storage.create_bucket(job_id)
        storage.upload_files(job_id, [str(smoke_script)])
        container_files = [
            str(SKILL_DIR / "container" / "onstart.sh"),
            str(SKILL_DIR / "container" / "progress_reporter.py"),
            str(SKILL_DIR / "container" / "gpu2runpod_observer.py"),
        ]
        storage.upload_files(job_id, container_files, prefix="")
        storage.upload_config(job_id, {
            "experiment_cmd": "python3 -u smoke_train.py",
            "job_id": job_id,
        })
        check(True, "Upload scripts + container files to storage")

        # Verify uploads via head_object (list_objects_v2 broken on RunPod S3)
        required_keys = {
            "onstart.sh":             f"{job_id}/onstart.sh",
            "progress_reporter.py":   f"{job_id}/progress_reporter.py",
            "gpu2runpod_observer.py": f"{job_id}/gpu2runpod_observer.py",
            "smoke_train.py":         f"{job_id}/data/smoke_train.py",
        }
        missing = []
        for name, key in required_keys.items():
            try:
                storage.s3.head_object(Bucket=storage.volume_id, Key=key)
            except Exception:
                missing.append(name)
        check(len(missing) == 0, "All container files uploaded",
              f"missing: {missing}" if missing else "all present")

        # Prepare SSH public key
        ssh_key = SKILL_DIR / "keys" / "ssh" / "gpu2runpod_ed25519"
        pub_key = Path(str(ssh_key) + ".pub").read_text().strip()
        sc = cfg["storage"]

        env_vars = {
            "RUNPOD_STORAGE_ENDPOINT":   sc.get("endpoint", "https://s3api-us-ks-2.runpod.io/"),
            "RUNPOD_STORAGE_ACCESS_KEY": sc["access_key"],
            "RUNPOD_STORAGE_SECRET_KEY": sc["secret_key"],
            "RUNPOD_STORAGE_VOLUME_ID":  sc["volume_id"],
            "RUNPOD_STORAGE_JOB_PREFIX": job_id,
            "HF_TOKEN": cfg.get("hf_token", ""),
            "HUGGING_FACE_HUB_TOKEN": cfg.get("hf_token", ""),
            "JOB_ID": job_id,
            "EXPERIMENT_CMD": "python3 -u smoke_train.py",
            "RESULTS_PATTERN": "results/**/*",
            "PUBLIC_KEY": pub_key,
        }

        # Create pod
        print(f"    [INFO] Creating pod ({gpu_type}, COMMUNITY)...")
        pod = rp.create_pod(
            name=f"smoke-{job_id[:16]}",
            gpu_type=gpu_type,
            env_vars=env_vars,
            disk_gb=20,
            cloud_type="COMMUNITY",
        )
        pod_id = pod.get("id") or pod.get("podId")
        check(bool(pod_id), f"Pod created", f"pod_id={pod_id}")

        # Wait for RUNNING + SSH port
        print(f"    [INFO] Waiting for pod to boot...")
        t0 = time.time()
        booted = rp.wait_for_running(pod_id, timeout=300)
        boot_time = int(time.time() - t0)
        check(booted, f"Pod reached RUNNING state in {boot_time}s")
        if not booted:
            raise RuntimeError("Pod failed to boot")

        # Get SSH info
        conn = rp.get_connection_info(pod_id)
        ssh_host = conn["ssh_host"]
        ssh_port = conn["ssh_port"]
        check(bool(ssh_host) and bool(ssh_port), f"SSH endpoint available",
              f"{ssh_host}:{ssh_port}")

        # SSH health check
        ssh_ok = rp.ssh_health_check(ssh_host, ssh_port, str(ssh_key))
        check(ssh_ok, "SSH health check passes")
        if not ssh_ok:
            raise RuntimeError("SSH health check failed")

        # Bootstrap: source Docker env vars (not inherited by SSH) then download + run onstart.sh
        _env_source = (
            "_tmpenv=$(mktemp); "
            "while IFS= read -r -d '' _e; do "
            "_k=\"${_e%%=*}\"; _v=\"${_e#*=}\"; "
            "case \"$_k\" in "
            "RUNPOD_STORAGE*|JOB_ID|EXPERIMENT_CMD|RESULTS_PATTERN|HF_TOKEN|HUGGING_FACE*|PUBLIC_KEY) "
            "printf 'export %s=%q\\n' \"$_k\" \"$_v\" >> \"$_tmpenv\";; "
            "esac; "
            "done < /proc/1/environ; "
            "source \"$_tmpenv\"; rm -f \"$_tmpenv\""
        )
        bootstrap_cmd = (
            f"{_env_source}; "
            f"echo \"[bootstrap] env sourced ep=$RUNPOD_STORAGE_ENDPOINT vol=$RUNPOD_STORAGE_VOLUME_ID pfx=$RUNPOD_STORAGE_JOB_PREFIX\"; "
            f"pip install -q boto3 2>/dev/null; "
            f"python3 -c \""
            f"import boto3, os, re, sys; "
            f"from botocore.config import Config; "
            f"ep=os.environ.get('RUNPOD_STORAGE_ENDPOINT',''); "
            f"vol=os.environ.get('RUNPOD_STORAGE_VOLUME_ID',''); "
            f"pfx=os.environ.get('RUNPOD_STORAGE_JOB_PREFIX',''); "
            f"print(f'[bootstrap] ep={{ep}} vol={{vol}} pfx={{pfx}}',file=sys.stderr); "
            f"assert ep and vol and pfx, f'Missing env ep={{ep!r}} vol={{vol!r}} pfx={{pfx!r}}'; "
            f"m=re.search(r's3api-([a-z0-9-]+)\\\\.runpod\\\\.io',ep); "
            f"region=m.group(1) if m else 'us-ks-2'; "
            f"s3=boto3.client('s3',endpoint_url=ep,"
            f"aws_access_key_id=os.environ['RUNPOD_STORAGE_ACCESS_KEY'],"
            f"aws_secret_access_key=os.environ['RUNPOD_STORAGE_SECRET_KEY'],"
            f"region_name=region,"
            f"config=Config(retries={{'max_attempts':5}},s3={{'addressing_style':'path'}})); "
            f"s3.download_file(vol, pfx+'/onstart.sh', '/tmp/onstart.sh'); "
            f"print('[bootstrap] onstart.sh downloaded OK',file=sys.stderr)\"; "
            f"chmod +x /tmp/onstart.sh; "
            f"nohup bash /tmp/onstart.sh > /tmp/job.log 2>&1 & echo \"BOOTSTRAP_PID:$!\""
        )
        result = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
             "-o", "ConnectTimeout=15", "-i", str(ssh_key),
             "-p", str(ssh_port), f"root@{ssh_host}", bootstrap_cmd],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
        )
        boot_ok = result.returncode == 0 and "BOOTSTRAP_PID:" in result.stdout
        if result.stdout.strip():
            print(f"    [INFO] Bootstrap stdout: {result.stdout.strip()[:300]}")
        if result.stderr.strip():
            print(f"    [INFO] Bootstrap stderr: {result.stderr.strip()[:300]}")
        check(boot_ok, "Bootstrap started on pod",
              result.stdout.strip()[:100] if boot_ok else result.stderr.strip()[:200])

        import threading

        # Stream SSH pod logs in background thread for real-time visibility
        _log_proc = subprocess.Popen(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
             "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15",
             "-i", str(ssh_key), "-p", str(ssh_port), f"root@{ssh_host}",
             "tail -f /tmp/job.log 2>/dev/null"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        _pod_logs = []

        def _stream_pod_log():
            try:
                for line in iter(_log_proc.stdout.readline, b""):
                    decoded = line.decode("utf-8", errors="replace").rstrip()
                    if decoded:
                        _pod_logs.append(decoded)
                        print(f"    [pod] {decoded}", flush=True)
            except Exception:
                pass

        threading.Thread(target=_stream_pod_log, daemon=True).start()

        # Poll for progress + done (max 10 min)
        print("    [INFO] Waiting for job to complete (max 10 min)...")
        deadline = time.time() + 600
        progress_seen = False
        gpu_metrics_seen = False
        done_info = None
        last_phase = ""
        _last_pod_log_check = time.time()

        while time.time() < deadline:
            time.sleep(8)

            # Periodically read pod log via SSH if tail stream is silent
            elapsed_since_log = time.time() - _last_pod_log_check
            if elapsed_since_log > 30 and not _pod_logs:
                try:
                    r = subprocess.run(
                        ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
                         "-o", "ConnectTimeout=5", "-i", str(ssh_key),
                         "-p", str(ssh_port), f"root@{ssh_host}",
                         "tail -20 /tmp/job.log 2>/dev/null || echo '[no job.log]'"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
                    )
                    if r.stdout.strip():
                        print(f"    [pod-poll] {r.stdout.strip()[:500]}")
                    _last_pod_log_check = time.time()
                except Exception:
                    pass

            # Check GPU metrics
            if not gpu_metrics_seen:
                try:
                    resp = storage.s3.get_object(
                        Bucket=storage.volume_id, Key=f"{job_id}/gpu_metrics.json"
                    )
                    metrics = json.loads(resp["Body"].read())
                    gpu_metrics_seen = True
                    gpu = metrics.get("current", {}).get("gpu", {})
                    mem_used = gpu.get("mem_used_gb", "?")
                    mem_total = gpu.get("mem_total_gb", "?")
                    util = gpu.get("gpu_util_pct", "?")
                    temp = gpu.get("temperature_c", "?")
                    print(f"    [INFO] GPU observer: {util}% util, {mem_used}/{mem_total}GB, {temp}C")
                except Exception:
                    pass

            # Check progress
            progress = storage.get_progress(job_id)
            if progress:
                progress_seen = True
                phase_now = progress.get("phase", "")
                if phase_now != last_phase:
                    print(f"    [INFO] Progress phase: {phase_now}")
                    last_phase = phase_now
                step = progress.get("step", "")
                loss = progress.get("loss", "")
                if step and loss:
                    print(f"    [INFO] Step {step}/{progress.get('total','?')} loss={loss}")

            # Check done
            done_info = storage.get_done(job_id)
            if done_info:
                break

            # Check pod still alive
            if not rp.is_pod_alive(pod_id):
                print("    [WARN] Pod is no longer alive")
                break

        check(progress_seen, "Progress reporter uploaded progress.json")
        check(gpu_metrics_seen, "GPU observer uploaded gpu_metrics.json")

        if done_info:
            status = done_info.get("status", "unknown")
            exit_code = done_info.get("exit_code", "?")
            n_files = len(done_info.get("files", {}))
            check(status == "success", f"Job completed successfully",
                  f"status={status}, exit_code={exit_code}, files={n_files}")
        else:
            check(False, "Job completed (done.json appeared)", "timeout or pod died")

        # Check TensorBoard started
        try:
            result = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=3", "-o", "StrictHostKeyChecking=no",
                 "-o", "BatchMode=yes", "-i", str(ssh_key),
                 "-p", str(ssh_port), f"root@{ssh_host}",
                 "curl -s -o /dev/null -w '%{http_code}' http://localhost:6006/ 2>/dev/null || echo 000"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
            )
            tb_code = result.stdout.strip().replace("'", "")
            check(tb_code == "200", "TensorBoard running on pod:6006", f"HTTP {tb_code}")
        except Exception as e:
            check(False, "TensorBoard check", str(e))

        # Download results — use done.json file list (list_objects_v2 broken on RunPod S3)
        with tempfile.TemporaryDirectory() as dl_dir:
            manifest_keys = list(done_info.get("files", {}).keys()) if done_info else None
            downloaded = storage.download_results(job_id, dl_dir, manifest_keys=manifest_keys)
            check(len(downloaded) > 0, f"Download results ({len(downloaded)} files)")

            # Validate smoke_result.txt
            result_file = Path(dl_dir) / "smoke_result.txt"
            if result_file.exists():
                content = result_file.read_text()
                check("STATUS: PASS" in content, "smoke_result.txt: STATUS: PASS")
                gpu_line = next((l for l in content.splitlines() if l.startswith("GPU:")), "")
                if gpu_line:
                    print(f"    [INFO] {gpu_line}")
                vram_line = next((l for l in content.splitlines() if l.startswith("VRAM_GB:")), "")
                if vram_line:
                    print(f"    [INFO] {vram_line}")
            else:
                check(False, "smoke_result.txt present in results")

            # Check TensorBoard logs downloaded
            tb_dirs = list(Path(dl_dir).rglob("tb_runs"))
            check(len(tb_dirs) > 0, "TensorBoard runs in results")

    except KeyboardInterrupt:
        print("\n    [WARN] Interrupted by user")
    except Exception as e:
        check(False, f"End-to-end pipeline error", str(e))
        import traceback
        traceback.print_exc()

    finally:
        # Stop SSH log streaming
        try:
            _log_proc.kill()
        except Exception:
            pass

        # Cleanup
        if pod_id and not keep_pod:
            try:
                rp.terminate_pod(pod_id)
                check(True, f"Pod {pod_id} terminated")
            except Exception as e:
                check(False, f"Pod {pod_id} terminate", str(e))
        elif pod_id and keep_pod:
            print(f"    [INFO] Pod {pod_id} kept alive (--keep-pod)")

        try:
            storage.delete_job(job_id)
            # Verify cleanup via head_object on a known key (listing unreliable on RunPod S3)
            cleanup_ok = True
            for key in list(required_keys.values())[:2]:
                try:
                    storage.s3.head_object(Bucket=storage.volume_id, Key=key)
                    cleanup_ok = False  # still exists
                    break
                except Exception:
                    pass  # expected: 404 = deleted
            check(cleanup_ok, "Storage job prefix cleaned up")
        except Exception as e:
            check(False, "Storage cleanup", str(e))

        # Clean temp script
        smoke_script = SKILL_DIR / "jobs" / "smoke_train.py"
        if smoke_script.exists():
            smoke_script.unlink()


# ─── Main ────────────────────────────────────────────────────────────────────

def _kill_orphans():
    """Terminate any leftover smoke pods before starting a new run."""
    try:
        import runpod_manager as rp
        rp._init()
        import runpod
        pods = runpod.get_pods() or []
        orphans = [p for p in pods if (p.get("name", "").startswith("smoke-"))]
        if orphans:
            print(f"  [pre-flight] Terminating {len(orphans)} orphaned smoke pod(s)...")
            for p in orphans:
                runpod.terminate_pod(p["id"])
                print(f"    Terminated: {p['id']} ({p.get('name')})")
    except Exception as e:
        print(f"  [pre-flight] Orphan check error: {e}")


def main():
    parser = argparse.ArgumentParser(description="GPU2RunPod smoke test")
    parser.add_argument("--phases", default="0,1,2,3,4",
                        help="Comma-separated phases to run (0=preflight 1=storage 2=api 3=ssh 4=e2e)")
    parser.add_argument("--gpu", default="RTX_3090",
                        help="GPU type for end-to-end test (default: RTX_3090 = cheapest reliable)")
    parser.add_argument("--keep-pod", action="store_true",
                        help="Keep pod alive after end-to-end test")
    args = parser.parse_args()

    phases_to_run = set(int(p) for p in args.phases.split(","))
    print(f"\nGPU2RunPod Smoke Test")
    print(f"Phases: {sorted(phases_to_run)}   GPU: {args.gpu}")
    if 4 in phases_to_run:
        _kill_orphans()

    cfg = {}
    gpu_info = None

    if 0 in phases_to_run:
        cfg = phase0_preflight() or {}

    if 1 in phases_to_run:
        phase1_storage(cfg)

    if 2 in phases_to_run:
        gpu_info = phase2_runpod_api(cfg, args.gpu)

    if 3 in phases_to_run:
        phase3_ssh_keys()

    if 4 in phases_to_run:
        if not cfg.get("storage"):
            print("\n  Skipping Phase 4: storage config missing")
        else:
            phase4_e2e(cfg, gpu_type=args.gpu, keep_pod=args.keep_pod)

    ok = summary()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
