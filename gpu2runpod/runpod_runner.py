"""
GPU2RunPod: Run GPU experiments on RunPod with RunPod S3-compatible storage.

Usage:
  python runpod_runner.py run --script "python3 -u train.py" --data file1.py file2.json --gpu RTX_4090
  python runpod_runner.py status
  python runpod_runner.py recover --job-id JOB_ID
  python runpod_runner.py cleanup --job-id JOB_ID
  python runpod_runner.py cleanup-all
"""

import argparse
import atexit
import json
import os
import signal
import subprocess
import sys
import time
import yaml
from datetime import datetime
from pathlib import Path

_child_processes = []


def _cleanup_children():
    for proc in _child_processes:
        try:
            proc.kill()
        except Exception:
            pass


atexit.register(_cleanup_children)


def _sigterm_handler(signum, frame):
    _cleanup_children()
    sys.exit(1)


signal.signal(signal.SIGTERM, _sigterm_handler)

SKILL_DIR = Path(__file__).parent
KEYS_DIR = SKILL_DIR / "keys"
JOBS_DIR = SKILL_DIR / "jobs"
LOGS_DIR = SKILL_DIR / "logs"
JOBS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
SSH_KEY = KEYS_DIR / "ssh" / "gpu2runpod_ed25519"

_log_fh = None


def _log(msg: str, also_print: bool = True):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    if also_print:
        _safe_print(line)
    if _log_fh is not None:
        try:
            _log_fh.write(line + "\n")
            _log_fh.flush()
        except Exception:
            pass

CONFIG_PATH = Path.home() / ".config" / "gpu2runpod" / "config.yaml"


def load_config() -> dict:
    config = {}
    if CONFIG_PATH.exists():
        config = yaml.safe_load(CONFIG_PATH.read_text()) or {}

    runpod_key = KEYS_DIR / "runpod.key"
    if runpod_key.exists():
        config.setdefault("runpod", {})["api_key"] = runpod_key.read_text().strip()

    storage_key = KEYS_DIR / "runpod_storage.key"
    if storage_key.exists():
        storage_config = json.loads(storage_key.read_text())
        config.setdefault("storage", {}).update(storage_config)

    hf_key = KEYS_DIR / "huggingface.key"
    if hf_key.exists():
        config["hf_token"] = hf_key.read_text().strip()

    return config


def _resolve_data_path(spec: str) -> Path:
    if ":" in spec and not Path(spec).exists():
        return Path(spec.rsplit(":", 1)[0])
    return Path(spec)


def generate_job_id(name: str) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    clean = name.lower().replace(" ", "-")[:20]
    return f"{clean}-{ts}"


def _ensure_ssh_key():
    """Generate SSH key pair if not present."""
    if SSH_KEY.exists():
        return SSH_KEY.read_text() if False else None  # key exists, no-op

    SSH_KEY.parent.mkdir(parents=True, exist_ok=True)
    print("  Generating SSH key pair for RunPod access...")
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(SSH_KEY), "-N", "", "-C", "gpu2runpod"],
        check=True, capture_output=True,
    )
    print(f"  SSH key created: {SSH_KEY}")


def _read_public_key() -> str:
    pub = Path(str(SSH_KEY) + ".pub")
    if pub.exists():
        return pub.read_text().strip()
    return ""


def _safe_print(text: str):
    try:
        print(text, flush=True)
    except (UnicodeEncodeError, UnicodeDecodeError):
        print(text.encode("ascii", errors="replace").decode("ascii"), flush=True)


def run_experiment(args):
    """Full lifecycle: provision storage, launch pod, bootstrap, monitor, download, cleanup."""
    global _log_fh
    import runpod_manager as rp
    from runpod_storage import RunPodStorage

    config = load_config()
    job_id = generate_job_id(args.name or "job")
    pod_id = None
    storage = None

    log_path = LOGS_DIR / f"{job_id}.log"
    _log_fh = open(log_path, "w", buffering=1, encoding="utf-8")

    _log(f"{'='*60}")
    _log(f"  GPU2RunPod: {job_id}")
    _log(f"  Script: {args.script}")
    _log(f"  GPU: {args.gpu}, Max: ${args.max_price}/hr, Cloud: {args.cloud}")
    _log(f"  Log file: {log_path}")
    _log(f"{'='*60}")

    job_info = {
        "job_id": job_id,
        "script": args.script,
        "data_files": args.data,
        "gpu": args.gpu,
        "max_price": args.max_price,
        "cloud_type": args.cloud,
        "docker_image": args.image,
        "started_at": datetime.now().isoformat(),
        "status": "provisioning",
    }
    job_path = JOBS_DIR / f"{job_id}.json"
    job_path.write_text(json.dumps(job_info, indent=2))

    if "storage" not in config or not config["storage"].get("volume_id"):
        _log("  ERROR: RunPod storage credentials missing. Check keys/runpod_storage.key")
        _log("  Required JSON fields: endpoint, access_key, secret_key, volume_id")
        return

    try:
        # 0. Local smoke test
        if not args.skip_smoke:
            _log("[0/6] Local smoke test (checking imports + dependencies)...")
            if not _local_smoke_test(args.data, args.script):
                _log("  Smoke test FAILED. Fix errors above before running on RunPod.")
                _log("  Use --skip-smoke to bypass (not recommended).")
                job_info["status"] = "smoke_test_failed"
                job_path.write_text(json.dumps(job_info, indent=2))
                return
            _log("  Smoke test passed")

        # 1. Init storage + upload
        _log("[1/6] Initializing RunPod storage + uploading data...")
        t0 = time.time()
        storage = RunPodStorage(config["storage"])
        storage.create_bucket(job_id)
        job_info["storage_job_id"] = job_id

        storage.upload_files(job_id, args.data)
        container_files = [
            str(SKILL_DIR / "container" / "onstart.sh"),
            str(SKILL_DIR / "container" / "progress_reporter.py"),
            str(SKILL_DIR / "container" / "gpu2runpod_observer.py"),
        ]
        storage.upload_files(job_id, container_files, prefix="")
        storage.upload_config(job_id, {
            "experiment_cmd": args.script,
            "results_pattern": args.results_pattern,
            "job_id": job_id,
        })
        _log(f"  Upload complete ({time.time()-t0:.1f}s)")

        # 2. Find GPU + pricing
        _log(f"[2/6] Searching for {args.gpu} (<=${args.max_price}/hr, {args.cloud})...")
        gpu_info = rp.search_gpu(args.gpu, max_price=args.max_price, cloud_type=args.cloud)
        if not gpu_info:
            raise RuntimeError(f"No {args.gpu} available at <=${args.max_price}/hr ({args.cloud})")
        cloud_type = gpu_info.get("_resolved_cloud_type", args.cloud)
        price = gpu_info.get("_resolved_price", 0)
        _log(f"  GPU found: {gpu_info.get('displayName', args.gpu)} @ ${price:.3f}/hr ({cloud_type})")

        data_size_gb = sum(
            p.stat().st_size for f in args.data
            for p in [_resolve_data_path(f)] if p.exists()
        ) / (1024**3)
        est = rp.estimate_cost(gpu_info, args.max_hours * 60, data_gb=max(data_size_gb, 0.01))
        phases = est["phases"]
        _log(f"  ETA: ~{est['total_minutes']:.0f} min total, ~${est['total_cost']:.4f}")
        _log(f"    upload={phases['r2_upload']:.0f}m  boot={phases['pod_boot']:.0f}m  "
              f"setup={phases['setup_and_download']:.0f}m  train={phases['training']:.0f}m  "
              f"fetch={phases['result_download']:.0f}m")
        job_info["estimated_cost"] = est["total_cost"]
        job_info["estimated_minutes"] = est["total_minutes"]

        # 3. Create pod
        _log("[3/6] Creating RunPod pod...")
        _ensure_ssh_key()
        pub_key = _read_public_key()
        hf_token = config.get("hf_token", "")
        sc = config["storage"]

        env_vars = {
            "RUNPOD_STORAGE_ENDPOINT":   sc.get("endpoint", "https://s3api-us-ks-2.runpod.io/"),
            "RUNPOD_STORAGE_ACCESS_KEY": sc["access_key"],
            "RUNPOD_STORAGE_SECRET_KEY": sc["secret_key"],
            "RUNPOD_STORAGE_VOLUME_ID":  sc["volume_id"],
            "RUNPOD_STORAGE_JOB_PREFIX": job_id,
            "HF_TOKEN": hf_token,
            "HUGGING_FACE_HUB_TOKEN": hf_token,
            "JOB_ID": job_id,
            "EXPERIMENT_CMD": args.script,
            "RESULTS_PATTERN": args.results_pattern,
            "PUBLIC_KEY": pub_key,
        }

        docker_image = args.image
        if docker_image == "auto":
            docker_image = rp.DEFAULT_IMAGE
            print(f"  Auto-selected image: {docker_image}")

        pod = rp.create_pod(
            name=f"gpu2runpod-{job_id[:20]}",
            gpu_type=args.gpu,
            image=docker_image,
            env_vars=env_vars,
            disk_gb=args.disk,
            cloud_type=cloud_type,
        )
        pod_id = pod.get("id") or pod.get("podId")
        if not pod_id:
            raise RuntimeError(f"Pod creation failed: {pod}")

        job_info["pod_id"] = pod_id
        job_info["status"] = "booting"
        job_path.write_text(json.dumps(job_info, indent=2))
        t_pod_created = time.time()
        _log(f"  Pod created: {pod_id} (image: {docker_image})")

        # 4. Wait for boot + SSH health check
        _log("[4/6] Waiting for pod to boot + SSH health check...")
        _log(f"  [timing] pod_created_at={datetime.now().isoformat()}")
        t_boot_start = time.time()
        if not rp.wait_for_running(pod_id, timeout=300):
            raise RuntimeError(f"Pod {pod_id} failed to enter RUNNING state")

        t_running = time.time()
        _log(f"  Pod RUNNING after {t_running - t_boot_start:.0f}s")

        conn = rp.get_connection_info(pod_id)
        ssh_host = conn["ssh_host"]
        ssh_port = conn["ssh_port"]
        _log(f"  SSH endpoint: {ssh_host}:{ssh_port}")

        t_ssh_start = time.time()
        if not rp.ssh_health_check(ssh_host, ssh_port, str(SSH_KEY)):
            raise RuntimeError(f"SSH health check failed for {ssh_host}:{ssh_port}")
        t_ssh_ok = time.time()
        _log(f"  SSH health check: OK ({t_ssh_ok - t_ssh_start:.0f}s)")
        _log(f"  [timing] boot={t_running-t_boot_start:.0f}s  ssh_ready={t_ssh_ok-t_running:.0f}s  total_to_ssh={t_ssh_ok-t_boot_start:.0f}s")

        job_info["status"] = "running"
        job_info["ssh_host"] = ssh_host
        job_info["ssh_port"] = ssh_port
        job_info["boot_seconds"] = round(t_running - t_boot_start)
        job_info["ssh_ready_seconds"] = round(t_ssh_ok - t_boot_start)
        job_path.write_text(json.dumps(job_info, indent=2))

        # Start TensorBoard tunnel in background thread
        import threading
        tb_result = {"url": ""}

        def _tb_bg():
            url = _setup_tensorboard(ssh_host, ssh_port, conn.get("tb_port"), timeout=180)
            tb_result["url"] = url
            if url:
                job_info["tensorboard_url"] = url
                job_path.write_text(json.dumps(job_info, indent=2))

        tb_thread = threading.Thread(target=_tb_bg, daemon=True)
        tb_thread.start()

        # 5. Bootstrap: run onstart.sh via SSH in background, tail log
        _log("[5/6] Bootstrapping pod (pip install + storage download + run job)...")
        # Source container env vars (Docker envs not inherited by SSH sessions)
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
            f"echo \"[bootstrap] ENV: ep=$RUNPOD_STORAGE_ENDPOINT vol=$RUNPOD_STORAGE_VOLUME_ID pfx=$RUNPOD_STORAGE_JOB_PREFIX\"; "
            f"pip install -q boto3 2>/dev/null; "
            f"python3 -c \""
            f"import boto3, os, re, sys; "
            f"from botocore.config import Config; "
            f"ep=os.environ.get('RUNPOD_STORAGE_ENDPOINT',''); "
            f"vol=os.environ.get('RUNPOD_STORAGE_VOLUME_ID',''); "
            f"pfx=os.environ.get('RUNPOD_STORAGE_JOB_PREFIX',''); "
            f"print(f'[bootstrap] ep={{ep}} vol={{vol}} pfx={{pfx}}', file=sys.stderr); "
            f"assert ep and vol and pfx, f'Missing env: ep={{ep!r}} vol={{vol!r}} pfx={{pfx!r}}'; "
            f"m=re.search(r's3api-([a-z0-9-]+)\\\\.runpod\\\\.io',ep); "
            f"region=m.group(1) if m else 'us-ks-2'; "
            f"s3=boto3.client('s3',endpoint_url=ep,"
            f"aws_access_key_id=os.environ['RUNPOD_STORAGE_ACCESS_KEY'],"
            f"aws_secret_access_key=os.environ['RUNPOD_STORAGE_SECRET_KEY'],"
            f"region_name=region,"
            f"config=Config(retries={{'max_attempts':5}},s3={{'addressing_style':'path'}})); "
            f"vol=os.environ['RUNPOD_STORAGE_VOLUME_ID']; "
            f"pfx=os.environ['RUNPOD_STORAGE_JOB_PREFIX']; "
            f"s3.download_file(vol, pfx+'/onstart.sh', '/tmp/onstart.sh'); "
            f"print('[bootstrap] onstart.sh downloaded OK', file=sys.stderr)\"; "
            f"chmod +x /tmp/onstart.sh; "
            f"nohup bash /tmp/onstart.sh > /tmp/job.log 2>&1 & echo \"BOOTSTRAP_PID:$!\""
        )

        result = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
             "-o", "ConnectTimeout=15", "-i", str(SSH_KEY),
             "-p", str(ssh_port), f"root@{ssh_host}",
             bootstrap_cmd],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=90,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Bootstrap failed: {result.stderr[:500]}")
        t_bootstrap = time.time()
        _log(f"  Bootstrap started: {result.stdout.strip()[:200]}")
        _log(f"  [timing] bootstrap_start={t_bootstrap - t_ssh_ok:.0f}s after SSH")

        # Start SSH log streaming in background thread
        log_proc = subprocess.Popen(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
             "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15",
             "-i", str(SSH_KEY), "-p", str(ssh_port), f"root@{ssh_host}",
             "tail -f /tmp/job.log 2>/dev/null"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        _child_processes.append(log_proc)

        def _stream_ssh_logs():
            try:
                for line in iter(log_proc.stdout.readline, b""):
                    decoded = line.decode("utf-8", errors="replace").rstrip()
                    if decoded:
                        _log(f"[pod] {decoded}")
            except Exception:
                pass

        log_thread = threading.Thread(target=_stream_ssh_logs, daemon=True)
        log_thread.start()

        # 6. Monitor via storage progress + SSH log stream
        _log("[6/6] Monitoring (Ctrl+C to detach, use 'recover' to reconnect)...")
        monitor_job(storage, job_id, pod_id, args.max_hours)

        # 7. Download results
        _log("[7] Downloading results...")
        t_dl = time.time()
        downloaded = storage.download_results(job_id, args.local_results)
        _log(f"  Downloaded {len(downloaded)} files to {args.local_results} ({time.time()-t_dl:.1f}s)")

        job_info["status"] = "completed"
        job_info["completed_at"] = datetime.now().isoformat()
        job_path.write_text(json.dumps(job_info, indent=2))

        _log(f"\n{'='*60}")
        _log(f"  COMPLETE: {job_id}")
        _log(f"  Results: {args.local_results}")
        if args.keep_alive and pod_id:
            _log(f"  Pod kept alive: {pod_id}")
            _log(f"  Destroy: python runpod_runner.py cleanup --job-id {job_id}")
        _log(f"{'='*60}")

    except KeyboardInterrupt:
        _log(f"\n  Detached. Job continues on RunPod.")
        _log(f"  Recover: python runpod_runner.py recover --job-id {job_id}")
        job_info["status"] = "detached"
        job_path.write_text(json.dumps(job_info, indent=2))
        return

    except Exception as e:
        _log(f"\n  ERROR: {e}")
        import traceback
        _log(traceback.format_exc(), also_print=False)
        job_info["status"] = "failed"
        job_info["error"] = str(e)
        job_path.write_text(json.dumps(job_info, indent=2))

    finally:
        if job_info.get("status") != "detached":
            _cleanup(pod_id, storage, job_id, job_info, job_path,
                     keep_pod=getattr(args, "keep_alive", False),
                     auto_destroy=getattr(args, "auto_destroy", False),
                     local_results=getattr(args, "local_results", None))
        if _log_fh is not None:
            try:
                _log_fh.flush()
                _log_fh.close()
            except Exception:
                pass


def _local_smoke_test(data_files: list, script_cmd: str) -> bool:
    import subprocess as sp

    py_files = [str(_resolve_data_path(f)) for f in data_files
                if _resolve_data_path(f).suffix == ".py" and _resolve_data_path(f).exists()]
    if not py_files:
        print("  No Python files in --data, skipping")
        return True

    local_modules = {Path(f).stem for f in py_files}

    for py_file in py_files:
        code = Path(py_file).read_text(errors="replace")
        try:
            compile(code, py_file, "exec")
            print(f"  {Path(py_file).name}: syntax OK")
        except SyntaxError as e:
            print(f"  {Path(py_file).name}: SYNTAX ERROR: {e}")
            return False

        imports = []
        for line in code.split("\n"):
            line = line.strip()
            if line.startswith("import ") or line.startswith("from "):
                if line.startswith("from "):
                    module = line.split()[1].split(".")[0]
                else:
                    module = line.split()[1].split(".")[0].rstrip(",")
                stdlib = {"os", "sys", "json", "time", "pathlib", "shutil",
                          "glob", "re", "math", "collections", "functools",
                          "typing", "dataclasses", "argparse", "hashlib",
                          "abc", "io", "copy", "logging", "warnings"}
                if module not in stdlib and module not in local_modules:
                    imports.append(module)

        for module in sorted(set(imports)):
            result = sp.run(
                [sys.executable, "-c", f"import {module}"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            )
            if result.returncode == 0:
                print(f"  import {module}: OK")
            else:
                err = result.stderr.strip().split("\n")[-1] if result.stderr else "unknown"
                print(f"  import {module}: MISSING ({err})")
                return False

    for py_file in py_files:
        code = Path(py_file).read_text(errors="replace")
        if "SummaryWriter" in code or "tensorboard" in code.lower():
            print(f"  {Path(py_file).name}: TensorBoard logging: OK")
        elif "train" in Path(py_file).name.lower():
            print(f"  WARNING: {Path(py_file).name} does not use TensorBoard (SummaryWriter)")

    return True


def _setup_tensorboard(ssh_host: str, ssh_port: int, tb_direct_port: int = None,
                       timeout: int = 180) -> str:
    import subprocess as sp
    import webbrowser

    print("  TensorBoard: checking in background...")
    start = time.time()
    tb_ready = False

    while time.time() - start < timeout:
        if ssh_host and ssh_port and SSH_KEY.exists():
            try:
                result = sp.run(
                    ["ssh", "-o", "ConnectTimeout=3", "-o", "StrictHostKeyChecking=no",
                     "-o", "BatchMode=yes", "-i", str(SSH_KEY),
                     "-p", str(ssh_port), f"root@{ssh_host}",
                     "curl -s -o /dev/null -w '%{http_code}' http://localhost:6006/ 2>/dev/null || echo 000"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
                )
                code = result.stdout.strip().replace("'", "")
                if code == "200":
                    tb_ready = True
                    break
            except Exception:
                pass
        time.sleep(5)

    if not tb_ready:
        print(f"\n  TensorBoard: not ready after {timeout}s")
        return ""

    print()
    tb_url = ""
    if SSH_KEY.exists():
        try:
            tunnel_proc = subprocess.Popen(
                ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
                 "-i", str(SSH_KEY), "-p", str(ssh_port), f"root@{ssh_host}",
                 "-L", "6006:localhost:6006", "-N"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            _child_processes.append(tunnel_proc)
            tb_url = "http://localhost:6006"
        except Exception as e:
            print(f"  TensorBoard tunnel failed: {e}")
            return ""

    if tb_url:
        print(f"  +----------------------------------------------+")
        print(f"  |  TensorBoard: {tb_url:<29s} |")
        print(f"  +----------------------------------------------+")
        try:
            webbrowser.open(tb_url)
            print(f"  (opened in browser)")
        except Exception:
            print(f"  (open the link above in your browser)")

    return tb_url


_last_phase = None


def _display_progress(progress: dict, elapsed: float):
    global _last_phase
    step = progress.get("step", "?")
    total = progress.get("total", "?")
    loss = progress.get("loss", "")
    epoch = progress.get("epoch", "")
    phase = progress.get("phase", "")
    val_loss = progress.get("val_loss", "")
    accuracy = progress.get("accuracy", "")
    mins = elapsed / 60

    PHASE_LABELS = {
        "model_loading":    "Loading model",
        "data_loading":     "Loading data",
        "tokenizing":       "Tokenizing",
        "downloading_weights": "Downloading weights",
        "training":         "Training",
        "evaluating":       "Evaluating",
        "saving_model":     "Saving model",
        "uploading_results": "Uploading results",
        "done":             "Done",
    }
    if phase and phase != _last_phase and phase != "unknown":
        _safe_print(f"\n  >> Phase: {PHASE_LABELS.get(phase, phase)}")
        _last_phase = phase

    parts = []
    if str(step).isdigit() and str(total).isdigit():
        pct = int(step) / int(total) * 100
        bar = "=" * int(pct / 5) + ">" + " " * (20 - int(pct / 5))
        parts.append(f"[{bar}] {pct:.0f}% ({step}/{total})")
    if loss:
        parts.append(f"loss={loss}")
    if epoch:
        parts.append(f"epoch={epoch}")
    if val_loss:
        parts.append(f"val_loss={val_loss}")
    if accuracy:
        parts.append(f"acc={accuracy}")
    parts.append(f"t={mins:.1f}m")

    if parts:
        msg = f"  PROGRESS: {' | '.join(parts)}"
        _safe_print(msg)
        if _log_fh is not None:
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            try:
                _log_fh.write(f"[{ts}] {msg}\n")
                _log_fh.flush()
            except Exception:
                pass


def monitor_job(storage, job_id: str, pod_id: str, max_hours: float):
    import runpod_manager as rp

    start = time.time()
    max_seconds = max_hours * 3600
    stale_count = 0
    last_check = 0
    poll_interval = 5

    print(f"  Polling storage every {poll_interval}s...")

    while True:
        elapsed = time.time() - start
        if elapsed > max_seconds:
            _log(f"\n  TIMEOUT after {max_hours}h")
            break

        now = time.time()
        if now - last_check >= poll_interval:
            done = storage.get_done(job_id)
            if done:
                status = done.get("status", "unknown")
                exit_code = done.get("exit_code", "?")
                _log(f"\n  Job finished: status={status} exit_code={exit_code} elapsed={int(elapsed)}s")
                if _log_fh is not None:
                    try:
                        _log_fh.write(f"  done.json: {json.dumps(done)}\n")
                    except Exception:
                        pass
                return

            error = storage.get_error(job_id)
            if error:
                _log(f"\n  Job error: {error}")
                return

            progress = storage.get_progress(job_id)
            if progress:
                _display_progress(progress, elapsed)
                # Log recent lines from pod to file
                if _log_fh is not None and progress.get("recent_lines"):
                    try:
                        for rl in progress["recent_lines"]:
                            _log_fh.write(f"  [recent] {rl}\n")
                        _log_fh.flush()
                    except Exception:
                        pass
                stale_count = 0
            else:
                stale_count += 1
                if stale_count % 6 == 0:
                    _log(f"  [monitor] no progress for {stale_count * poll_interval}s...", also_print=False)

            if stale_count > 0 and stale_count % 12 == 0:
                alive = rp.is_pod_alive(pod_id)
                stale_secs = stale_count * poll_interval
                if not alive:
                    _log(f"\n  Pod {pod_id} is no longer running ({stale_secs}s of no activity)")
                    return
                if stale_count >= 24:
                    _log(f"\n  WARNING: No progress for {stale_secs}s (pod still alive)")

            last_check = now

        time.sleep(poll_interval)


def _cleanup(pod_id, storage, job_id, job_info, job_path,
             keep_pod=False, auto_destroy=False, local_results=None):
    if job_info.get("status") == "detached":
        return

    import runpod_manager as rp

    _log("\n  Cleanup...")

    ok = False
    if local_results and Path(local_results).exists():
        files = [f for f in Path(local_results).rglob("*") if f.is_file() and f.stat().st_size > 0]
        ok = bool(files)
        summary = f"{len(files)} non-empty files" if files else "no files"
        _log(f"  Results validation: {'PASS' if ok else 'FAIL'} - {summary}")

    destroy_pod = auto_destroy and ok and not keep_pod
    delete_job_data = auto_destroy and ok

    if pod_id:
        if destroy_pod:
            try:
                rp.terminate_pod(pod_id)
                _log(f"  [cleanup] Pod {pod_id} terminated")
            except Exception as e:
                _log(f"  [cleanup] Pod terminate failed: {e}")
        else:
            reason = "--keep-alive" if keep_pod else (
                "results invalid" if not ok else "default (no --auto-destroy)"
            )
            _log(f"  Pod {pod_id} RETAINED ({reason})")
            _log(f"    Destroy: python runpod_runner.py cleanup --job-id {job_info.get('job_id','?')}")

    if storage and job_id:
        if delete_job_data:
            try:
                storage.delete_job(job_id)
                _log(f"  [cleanup] Storage job prefix {job_id}/ deleted")
            except Exception as e:
                _log(f"  [cleanup] Storage delete failed: {e}")
        else:
            reason = "results invalid" if not ok else "default (no --auto-destroy)"
            _log(f"  Storage prefix {job_id}/ RETAINED ({reason})")

    _log("  Cleanup complete")


def cmd_status(args):
    job_files = sorted(JOBS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not job_files:
        print("No jobs found.")
        return
    print(f"\n{'Job ID':<40} {'Status':<15} {'Pod':<25} {'Started'}")
    print("-" * 100)
    for jf in job_files[:20]:
        info = json.loads(jf.read_text())
        print(f"  {info.get('job_id','?'):<38} {info.get('status','?'):<15} "
              f"{str(info.get('pod_id','')):<25} {info.get('started_at','')[:16]}")


def cmd_recover(args):
    """Reconnect to a detached job and tail its logs."""
    job_path = JOBS_DIR / f"{args.job_id}.json"
    if not job_path.exists():
        print(f"Job not found: {args.job_id}")
        return

    job_info = json.loads(job_path.read_text())
    pod_id = job_info.get("pod_id")
    bucket = job_info.get("r2_bucket")
    ssh_host = job_info.get("ssh_host")
    ssh_port = job_info.get("ssh_port")
    max_hours = 6.0

    print(f"  Recovering job: {args.job_id}")
    print(f"  Pod: {pod_id}, SSH: root@{ssh_host}:{ssh_port}")

    config = load_config()
    storage = None
    if "storage" in config:
        from runpod_storage import RunPodStorage
        storage = RunPodStorage(config["storage"])

    if ssh_host and ssh_port and SSH_KEY.exists():
        print("  Attaching SSH log tail...")
        log_proc = subprocess.Popen(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
             "-i", str(SSH_KEY), "-p", str(ssh_port), f"root@{ssh_host}",
             "tail -f /tmp/job.log 2>/dev/null"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        _child_processes.append(log_proc)
        import threading

        def _tail():
            for line in iter(log_proc.stdout.readline, b""):
                _safe_print(f"  [pod] {line.decode('utf-8', errors='replace').rstrip()}")
        threading.Thread(target=_tail, daemon=True).start()

    if storage and pod_id:
        try:
            monitor_job(storage, args.job_id, pod_id, max_hours)
            downloaded = storage.download_results(args.job_id, f"results_{args.job_id}")
            print(f"  Downloaded {len(downloaded)} files to results_{args.job_id}/")
        except KeyboardInterrupt:
            print("\n  Detached again.")


def cmd_cleanup(args):
    """Force-terminate a job's pod and/or R2 bucket."""
    import runpod_manager as rp

    job_path = JOBS_DIR / f"{args.job_id}.json"
    if not job_path.exists():
        print(f"Job not found: {args.job_id}")
        return

    job_info = json.loads(job_path.read_text())
    pod_id = job_info.get("pod_id")
    bucket = job_info.get("r2_bucket")

    if pod_id:
        print(f"  Terminating pod: {pod_id}")
        try:
            rp.terminate_pod(pod_id)
            print(f"  Pod {pod_id} terminated")
        except Exception as e:
            print(f"  Pod terminate error: {e}")

    config = load_config()
    if "storage" in config and job_info.get("storage_job_id"):
        from runpod_storage import RunPodStorage
        storage = RunPodStorage(config["storage"])
        storage.delete_job(job_info["storage_job_id"])

    job_info["status"] = "cleaned"
    job_path.write_text(json.dumps(job_info, indent=2))
    print("  Cleanup complete")


def cmd_cleanup_all(args):
    """Sweep all running pods and R2 buckets created by this skill."""
    import runpod_manager as rp

    print("  Sweeping orphaned pods...")
    try:
        pods = rp.get_pods()
        for pod in pods or []:
            name = pod.get("name", "")
            if name.startswith("gpu2runpod-"):
                pod_id = pod.get("id")
                status = pod.get("desiredStatus", "")
                print(f"  Terminating: {pod_id} ({name}) [{status}]")
                try:
                    rp.terminate_pod(pod_id)
                except Exception as e:
                    print(f"    Error: {e}")
    except Exception as e:
        print(f"  Pod sweep error: {e}")

    config = load_config()
    if "storage" in config:
        from runpod_storage import RunPodStorage
        storage = RunPodStorage(config["storage"])
        print("  Sweeping orphaned storage job prefixes...")
        try:
            jobs = storage.list_jobs()
            for job_prefix in jobs:
                print(f"  Deleting job prefix: {job_prefix}/")
                storage.delete_job(job_prefix)
        except Exception as e:
            print(f"  Storage sweep error: {e}")

    print("  Cleanup-all complete")


def main():
    parser = argparse.ArgumentParser(description="GPU2RunPod: Run GPU jobs on RunPod")
    sub = parser.add_subparsers(dest="cmd")

    # run
    run_p = sub.add_parser("run", help="Launch a new job")
    run_p.add_argument("--script", required=True, help="Command to run (e.g. 'python3 -u train.py')")
    run_p.add_argument("--data", nargs="+", default=[], help="Files to upload (local[:remote] syntax)")
    run_p.add_argument("--gpu", default="RTX_4090",
                       help="GPU type: RTX_4090, A100, H100, L40S, etc.")
    run_p.add_argument("--max-price", type=float, default=1.00, help="Max $/hr")
    run_p.add_argument("--cloud", default="COMMUNITY", choices=["COMMUNITY", "SECURE"])
    run_p.add_argument("--image", default="auto", help="Docker image (default: runpod/pytorch)")
    run_p.add_argument("--disk", type=int, default=40, help="Container disk GB")
    run_p.add_argument("--max-hours", type=float, default=6.0, help="Runtime cap in hours")
    run_p.add_argument("--keep-alive", action="store_true", help="Keep pod after job")
    run_p.add_argument("--auto-destroy", action="store_true",
                       help="Auto-terminate pod and delete bucket after success")
    run_p.add_argument("--skip-smoke", action="store_true", help="Skip local smoke test")
    run_p.add_argument("--name", default="", help="Job name prefix")
    run_p.add_argument("--results-pattern", default="results/**/*",
                       help="Glob pattern for result files on pod")
    run_p.add_argument("--local-results", default="results",
                       help="Local directory for downloaded results")

    # status
    sub.add_parser("status", help="Show recent jobs")

    # recover
    rec_p = sub.add_parser("recover", help="Reconnect to a detached job")
    rec_p.add_argument("--job-id", required=True)

    # cleanup
    cl_p = sub.add_parser("cleanup", help="Force-clean a specific job")
    cl_p.add_argument("--job-id", required=True)

    # cleanup-all
    sub.add_parser("cleanup-all", help="Sweep all orphaned pods and R2 buckets")

    args = parser.parse_args()
    if args.cmd is None:
        parser.print_help()
        return

    sys.path.insert(0, str(SKILL_DIR))

    if args.cmd == "run":
        run_experiment(args)
    elif args.cmd == "status":
        cmd_status(args)
    elif args.cmd == "recover":
        cmd_recover(args)
    elif args.cmd == "cleanup":
        cmd_cleanup(args)
    elif args.cmd == "cleanup-all":
        cmd_cleanup_all(args)


if __name__ == "__main__":
    main()
