"""
GPU2Vast: Run GPU experiments on vast.ai with ephemeral R2 storage.

Usage:
  python gpu_runner.py run --script "python train.py" --data file1.json file2.json --gpu A100
  python gpu_runner.py status
  python gpu_runner.py recover --job-id JOB_ID
  python gpu_runner.py cleanup --job-id JOB_ID
  python gpu_runner.py cleanup-all
"""

import argparse
import atexit
import json
import os
import signal
import sys
import time
import yaml
from datetime import datetime
from pathlib import Path

_child_processes = []


def _cleanup_children():
    """Kill any SSH tunnel or background processes on exit."""
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
JOBS_DIR.mkdir(exist_ok=True)

CONFIG_PATH = Path.home() / ".config" / "gpu2vast" / "config.yaml"


def load_config() -> dict:
    """Load config from file or keys directory."""
    config = {}
    if CONFIG_PATH.exists():
        config = yaml.safe_load(CONFIG_PATH.read_text())

    # Override with key files
    vastai_key = KEYS_DIR / "vastai.key"
    if vastai_key.exists():
        config.setdefault("vastai", {})["api_key"] = vastai_key.read_text().strip()

    r2_key = KEYS_DIR / "r2.key"
    if r2_key.exists():
        r2_config = json.loads(r2_key.read_text())
        config.setdefault("r2", {}).update(r2_config)

    return config


def generate_job_id(experiment_name: str) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    clean = experiment_name.lower().replace(" ", "-")[:20]
    return f"{clean}-{ts}"


def run_experiment(args):
    """Full lifecycle: provision R2, launch vast.ai, monitor, download, cleanup."""
    from r2_manager import R2Manager
    import vastai_manager as vast

    config = load_config()
    job_id = generate_job_id(args.name or "job")
    instance_id = None
    bucket = None
    r2 = None

    print(f"\n{'='*60}")
    print(f"  GPU2Vast: {job_id}")
    print(f"  Script: {args.script}")
    print(f"  GPU: {args.gpu}, Max: ${args.max_price}/hr")
    print(f"{'='*60}\n")

    job_info = {
        "job_id": job_id,
        "script": args.script,
        "data_files": args.data,
        "gpu": args.gpu,
        "max_price": args.max_price,
        "docker_image": args.image,
        "started_at": datetime.now().isoformat(),
        "status": "provisioning",
    }
    job_path = JOBS_DIR / f"{job_id}.json"
    job_path.write_text(json.dumps(job_info, indent=2))

    # Validate config
    if "r2" not in config or not config["r2"].get("account_id"):
        print("  ERROR: R2 credentials missing. Check keys/r2.key")
        job_info["status"] = "failed"
        job_info["error"] = "R2 credentials missing"
        job_path.write_text(json.dumps(job_info, indent=2))
        return

    try:
        # 1. Create R2 bucket
        print("[1/7] Creating R2 bucket...")
        r2 = R2Manager(config["r2"])
        bucket = r2.create_bucket(job_id)
        job_info["r2_bucket"] = bucket

        # 2. Upload data + container scripts
        print("[2/7] Uploading data...")
        r2.upload_files(bucket, args.data)
        container_files = [
            str(SKILL_DIR / "container" / "onstart.sh"),
            str(SKILL_DIR / "container" / "progress_reporter.py"),
            str(SKILL_DIR / "container" / "gpu2vast_observer.py"),
        ]
        r2.upload_files(bucket, container_files, prefix="")
        r2.upload_config(bucket, {
            "experiment_cmd": args.script,
            "results_pattern": args.results_pattern,
            "job_id": job_id,
        })
        print("  Upload complete")

        # 3. Find GPU
        offer_type = "bid" if args.spot else "on-demand"
        print(f"[3/7] Searching for {args.gpu} <= ${args.max_price}/hr ({offer_type})...")
        offers = vast.search_gpu(
            gpu_name=args.gpu, max_price=args.max_price, disk_gb=args.disk,
            offer_type=offer_type,
        )
        if not offers:
            raise RuntimeError(f"No {args.gpu} available at <=${args.max_price}/hr ({offer_type})")
        offer = offers[0]
        print(f"  Selected: {offer.get('gpu_name')} @ ${offer.get('dph_total', '?')}/hr (offer={offer['id']})")

        # Cost + ETA estimation
        data_size_gb = sum(Path(f).stat().st_size for f in args.data if Path(f).exists()) / (1024**3)
        est = vast.estimate_cost(offer, args.max_hours * 60, data_gb=max(data_size_gb, 0.01))
        phases = est["phases"]
        print(f"  ETA: ~{est['total_minutes']:.0f} min total, ~${est['total_cost']:.4f}")
        print(f"    upload={phases['r2_upload']:.0f}m  boot={phases['instance_boot']:.0f}m  "
              f"setup={phases['setup_and_download']:.0f}m  train={phases['training']:.0f}m  "
              f"fetch={phases['result_download']:.0f}m")
        job_info["estimated_cost"] = est["total_cost"]
        job_info["estimated_minutes"] = est["total_minutes"]

        # 4. Launch instance
        print("[4/7] Launching instance...")
        hf_token = ""
        hf_key_file = KEYS_DIR / "huggingface.key"
        if hf_key_file.exists():
            hf_token = hf_key_file.read_text().strip()

        # Dynamic image selection: analyze script imports if --image=auto
        docker_image = args.image
        if docker_image == "auto":
            script_files = [f for f in args.data if f.endswith(".py")]
            script_to_analyze = script_files[0] if script_files else None
            if script_to_analyze and Path(script_to_analyze).stat().st_size > 10_000_000:
                print(f"  Script too large for import analysis, using default image")
                docker_image = "vastai/pytorch"
            else:
                docker_image = vast.select_image(script_path=script_to_analyze)
            print(f"  Auto-selected image: {docker_image}")
        job_info["docker_image"] = docker_image

        env_vars = {
            "R2_ACCOUNT_ID": config["r2"]["account_id"],
            "R2_ACCESS_KEY": config["r2"]["access_key"],
            "R2_SECRET_KEY": config["r2"]["secret_key"],
            "R2_BUCKET": bucket,
            "HF_TOKEN": hf_token,
            "HUGGING_FACE_HUB_TOKEN": hf_token,
            "JOB_ID": job_id,
            "EXPERIMENT_CMD": args.script,
            "RESULTS_PATTERN": args.results_pattern,
        }
        if hf_token:
            print(f"  HuggingFace token: loaded (for gated models)")

        # Build bootstrap command: download onstart.sh from R2, then run it
        r2_endpoint = f"https://{config['r2']['account_id']}.r2.cloudflarestorage.com"
        onstart_cmd = (
            f"pip install -q boto3 2>/dev/null; "
            f"python3 -c \""
            f"import boto3; "
            f"s3=boto3.client('s3',endpoint_url='{r2_endpoint}',"
            f"aws_access_key_id='{config['r2']['access_key']}',"
            f"aws_secret_access_key='{config['r2']['secret_key']}',"
            f"region_name='auto'); "
            f"s3.download_file('{bucket}','onstart.sh','/tmp/onstart.sh')\"; "
            f"bash /tmp/onstart.sh"
        )

        # Launch with retry (some hosts have broken GPU/Docker setups)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                cur_offer = offers[attempt] if attempt < len(offers) else offer
                if attempt > 0:
                    print(f"  Retry {attempt + 1}/{max_retries}: offer {cur_offer['id']}")
                instance = vast.create_instance(
                    offer_id=cur_offer["id"],
                    docker_image=docker_image,
                    env_vars=env_vars,
                    onstart_cmd=onstart_cmd,
                    disk_gb=args.disk,
                )
                instance_id = instance.get("new_contract") or instance.get("instance_id")
                job_info["instance_id"] = instance_id
                job_info["status"] = "booting"
                job_path.write_text(json.dumps(job_info, indent=2))

                print("[5/7] Waiting for instance to boot + SSH health check...")
                if vast.wait_for_running(instance_id, timeout=300):
                    break
                print(f"  Boot failed on offer {cur_offer['id']}, trying next host...")
                vast.destroy_instance(instance_id)
                instance_id = None
            except RuntimeError as e:
                print(f"  Host error: {e}")
                if instance_id:
                    try:
                        vast.destroy_instance(instance_id)
                    except Exception:
                        pass
                    instance_id = None
                if attempt >= max_retries - 1:
                    raise
                continue

        if not instance_id:
            raise RuntimeError(f"All {max_retries} hosts failed to boot")
        print(f"  Instance {instance_id} is running")
        job_info["status"] = "running"
        job_path.write_text(json.dumps(job_info, indent=2))

        # 6. Open TensorBoard in browser
        tb_tunnel = None
        tb_url = _setup_tensorboard(vast, instance_id)
        if tb_url:
            job_info["tensorboard_url"] = tb_url
            job_path.write_text(json.dumps(job_info, indent=2))

        # 6. Monitor via R2 + stream vast.ai logs
        print("[6/7] Monitoring (Ctrl+C to detach, use 'recover' to reconnect)...")
        monitor_job(r2, bucket, job_id, instance_id, args.max_hours)

        # 7. Download results
        print("[7/7] Downloading results...")
        downloaded = r2.download_results(bucket, args.local_results)
        print(f"  Downloaded {len(downloaded)} files to {args.local_results}")

        job_info["status"] = "completed"
        job_info["completed_at"] = datetime.now().isoformat()
        job_path.write_text(json.dumps(job_info, indent=2))

        print(f"\n{'='*60}")
        print(f"  COMPLETE: {job_id}")
        print(f"  Results: {args.local_results}")
        if args.keep_alive and instance_id:
            print(f"  Instance kept alive: {instance_id}")
            print(f"  Rerun:   python gpu_runner.py rerun --instance-id {instance_id} --script '...' --data ...")
            print(f"  Destroy: python gpu_runner.py cleanup --job-id {job_id}")
        print(f"{'='*60}")

    except KeyboardInterrupt:
        print(f"\n  Detached. Job continues on vast.ai.")
        print(f"  Recover: python gpu_runner.py recover --job-id {job_id}")
        job_info["status"] = "detached"
        job_path.write_text(json.dumps(job_info, indent=2))
        return

    except Exception as e:
        print(f"\n  ERROR: {e}")
        job_info["status"] = "failed"
        job_info["error"] = str(e)
        job_path.write_text(json.dumps(job_info, indent=2))

    finally:
        _cleanup(vast, r2, instance_id, bucket, job_info, job_path,
                 keep_instance=getattr(args, 'keep_alive', False))


def _setup_tensorboard(vast, instance_id, timeout=120):
    """Wait for TensorBoard to start on the instance, then open it in the browser.

    Tries direct port access first (no SSH needed), falls back to SSH tunnel.
    Returns the URL that was opened, or empty string on failure.
    """
    import subprocess as sp
    import webbrowser

    print("  Waiting for TensorBoard to become available...")

    conn = vast.get_connection_info(instance_id)
    ssh_host = conn.get("ssh_host", "")
    ssh_port = conn.get("ssh_port", "")
    public_ip = conn.get("public_ip", "")

    # Try direct port first (check port mappings)
    tb_direct_port = conn.get("port_mappings", {}).get("6006/tcp", {}).get("host_port")

    # Poll until TensorBoard responds (via SSH check)
    key_path = KEYS_DIR / "ssh" / "gpu2vast_ed25519"
    start = time.time()
    tb_ready = False

    while time.time() - start < timeout:
        elapsed = int(time.time() - start)
        if ssh_host and ssh_port and key_path.exists():
            try:
                result = sp.run(
                    ["ssh", "-o", "ConnectTimeout=3", "-o", "StrictHostKeyChecking=no",
                     "-o", "BatchMode=yes", "-i", str(key_path),
                     "-p", str(ssh_port), f"root@{ssh_host}",
                     "curl -s -o /dev/null -w '%{http_code}' http://localhost:6006/ 2>/dev/null || echo 000"],
                    capture_output=True, text=True, timeout=10,
                )
                code = result.stdout.strip().replace("'", "")
                if code == "200":
                    tb_ready = True
                    break
                print(f"\r  TensorBoard: waiting ({elapsed}s, http={code})    ", end="", flush=True)
            except Exception:
                print(f"\r  TensorBoard: waiting ({elapsed}s)    ", end="", flush=True)
        else:
            print(f"\r  TensorBoard: waiting for SSH ({elapsed}s)    ", end="", flush=True)
        time.sleep(5)

    if not tb_ready:
        print(f"\n  TensorBoard: not ready after {timeout}s (training may still work)")
        return ""

    print()

    # Determine best URL and open browser
    tb_url = ""
    if tb_direct_port and public_ip:
        tb_url = f"http://{public_ip}:{tb_direct_port}"
        print(f"  TensorBoard (direct): {tb_url}")
    elif ssh_host and ssh_port and key_path.exists():
        # Open SSH tunnel in background
        try:
            tunnel_proc = sp.Popen(
                ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
                 "-i", str(key_path), "-p", str(ssh_port), f"root@{ssh_host}",
                 "-L", "6006:localhost:6006", "-N"],
                stdout=sp.DEVNULL, stderr=sp.DEVNULL,
            )
            _child_processes.append(tunnel_proc)
            tb_url = "http://localhost:6006"
            print(f"  TensorBoard (tunnel): {tb_url}")
        except Exception as e:
            print(f"  TensorBoard tunnel failed: {e}")
            return ""

    if tb_url:
        print()
        print(f"  ┌────────────────────────────────────────────┐")
        print(f"  │  TensorBoard: {tb_url:<29s}│")
        print(f"  └────────────────────────────────────────────┘")
        try:
            webbrowser.open(tb_url)
            print(f"  (opened in browser)")
        except Exception:
            print(f"  (open the link above in your browser)")

    return tb_url


def _cleanup(vast, r2, instance_id, bucket, job_info, job_path, keep_instance=False):
    """Destroy instance and delete bucket. Optionally keep instance for reuse."""
    if job_info.get("status") == "detached":
        return
    print("\n  Cleaning up...")
    if instance_id and not keep_instance:
        try:
            vast.destroy_instance(instance_id)
        except Exception as e:
            print(f"  [cleanup] Instance destroy failed: {e}")
    elif keep_instance and instance_id:
        print(f"  Instance {instance_id} kept alive (--keep-alive)")
    if bucket and r2:
        try:
            r2.delete_bucket(bucket)
        except Exception as e:
            print(f"  [cleanup] Bucket delete failed: {e}")
    print("  Cleanup complete")


def monitor_job(r2, bucket, job_id, instance_id, max_hours):
    """Poll R2 for progress and stream vast.ai instance logs."""
    import vastai_manager as vast

    start = time.time()
    max_seconds = max_hours * 3600
    stale_count = 0
    seen_log_lines = set()
    last_log_fetch = 0
    last_r2_check = 0
    poll_interval = 5

    print(f"  Polling every {poll_interval}s (logs + R2 progress)...")

    while True:
        elapsed = time.time() - start
        if elapsed > max_seconds:
            print(f"\n  TIMEOUT after {max_hours}h")
            break

        now = time.time()

        # Stream instance logs every 5s (fast, non-blocking)
        if instance_id and now - last_log_fetch >= poll_interval:
            _stream_logs(vast, instance_id, seen_log_lines, int(elapsed))
            last_log_fetch = now

        # Check R2 every 10s (slower S3 calls)
        if now - last_r2_check >= 10:
            # Check done
            done = r2.get_done(bucket)
            if done:
                status = done.get("status", "unknown")
                exit_code = done.get("exit_code", "?")
                # Final log fetch
                _stream_logs(vast, instance_id, seen_log_lines, int(elapsed))
                print(f"\n  Job finished: {status} (exit_code={exit_code}, {int(elapsed)}s)")
                if status != "success":
                    _print_final_logs(vast, instance_id, seen_log_lines)
                return

            # Check error
            error = r2.get_error(bucket)
            if error:
                print(f"\n  Job error: {error}")
                _print_final_logs(vast, instance_id, seen_log_lines)
                return

            # Check progress
            progress = r2.get_progress(bucket)
            if progress:
                _display_progress(progress, elapsed)
                stale_count = 0
            else:
                stale_count += 1

            # Check if instance died
            if stale_count > 0 and stale_count % 6 == 0:
                alive = vast.is_instance_alive(instance_id)
                stale_secs = stale_count * 10
                if not alive:
                    print(f"\n  Instance {instance_id} is no longer running ({stale_secs}s)")
                    _print_final_logs(vast, instance_id, seen_log_lines)
                    return
                if stale_count >= 18:
                    print(f"\n  WARNING: No progress for {stale_secs}s (instance still alive)")

            last_r2_check = now

        time.sleep(poll_interval)


_last_phase = None


def _display_progress(progress, elapsed):
    """Display rich progress info from R2 progress.json."""
    global _last_phase
    step = progress.get("step", "?")
    total = progress.get("total", "?")
    loss = progress.get("loss", "")
    epoch = progress.get("epoch", "")
    phase = progress.get("phase", "")
    gpu_info = progress.get("gpu", {})
    gpu_util = gpu_info.get("gpu_util", "?")
    gpu_mem = gpu_info.get("mem_used", "?")
    gpu_total = gpu_info.get("mem_total", "?")
    val_loss = progress.get("val_loss", "")
    accuracy = progress.get("accuracy", "")
    mins = elapsed / 60

    # Phase change announcement
    if phase and phase != _last_phase and phase != "unknown":
        phase_labels = {
            "model_loading": "Loading model",
            "data_loading": "Loading data",
            "tokenizing": "Tokenizing",
            "downloading_weights": "Downloading weights",
            "training": "Training",
            "evaluating": "Evaluating",
            "saving_model": "Saving model",
            "uploading_results": "Uploading results",
            "done": "Done",
        }
        label = phase_labels.get(phase, phase)
        _safe_print(f"\n  >> Phase: {label}")
        _last_phase = phase

    # Progress bar + metrics
    parts = []
    if str(step).isdigit() and str(total).isdigit():
        bar_pct = int(step) / int(total) * 100
        bar_len = 20
        filled = int(bar_pct / 100 * bar_len)
        bar = "#" * filled + "-" * (bar_len - filled)
        parts.append(f"[{bar}] {step}/{total}")
    if epoch:
        parts.append(f"ep={epoch}")
    if loss:
        parts.append(f"loss={loss}")
    if val_loss:
        parts.append(f"val={val_loss}")
    if accuracy:
        parts.append(f"acc={accuracy}")
    parts.append(f"GPU={gpu_util}%")
    if gpu_mem != "?" and gpu_total != "?":
        parts.append(f"VRAM={gpu_mem}/{gpu_total}MB")
    parts.append(f"{mins:.0f}min")

    _safe_print(f"\r  {'  '.join(parts)}    ")

    # Show recent log lines if available
    recent = progress.get("recent_lines", [])
    if recent and phase in ("training", "evaluating"):
        for line in recent[-2:]:
            if line not in _display_progress._shown:
                _display_progress._shown.add(line)
                _safe_print(f"    {line}")

_display_progress._shown = set()


def _safe_print(text):
    """Print text safely on Windows (handles Unicode chars in cp1252)."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode())


def _stream_logs(vast, instance_id, seen_lines, elapsed_s):
    """Fetch logs via vast.ai API + SSH (for onstart output)."""
    # vast.ai API logs (system/daemon logs)
    log_output = vast.get_logs(instance_id, tail=50)
    if log_output:
        for line in log_output.split("\n"):
            line = line.strip()
            if line and line not in seen_lines:
                seen_lines.add(line)
                _safe_print(f"  [{elapsed_s:3d}s] {line}")

    # SSH-based log streaming (application output from onstart.sh)
    ssh_output = _ssh_tail_log(vast, instance_id)
    if ssh_output:
        for line in ssh_output.split("\n"):
            line = line.strip()
            if line and line not in seen_lines:
                seen_lines.add(line)
                _safe_print(f"  [{elapsed_s:3d}s] [app] {line}")


def _ssh_tail_log(vast, instance_id, lines=30):
    """Tail the onstart log via SSH. Returns empty string on failure."""
    import subprocess
    info = vast.get_instance(instance_id)
    if not isinstance(info, dict):
        return ""
    ssh_host = info.get("ssh_host", "")
    ssh_port = info.get("ssh_port", "")
    if not ssh_host or not ssh_port:
        return ""
    key_path = KEYS_DIR / "ssh" / "gpu2vast_ed25519"
    if not key_path.exists():
        return ""
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no",
             "-o", "BatchMode=yes", "-i", str(key_path),
             "-p", str(ssh_port), f"root@{ssh_host}",
             f"tail -{lines} /var/log/onstart.log 2>/dev/null"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _print_final_logs(vast, instance_id, seen_lines):
    """Fetch last 100 lines for post-mortem."""
    if not instance_id:
        return
    print("  Fetching final logs...")
    log_output = vast.get_logs(instance_id, tail=100)
    if not log_output:
        print("  (no logs available)")
        return
    for line in log_output.split("\n"):
        line = line.strip()
        if line and line not in seen_lines:
            seen_lines.add(line)
            _safe_print(f"  [log] {line}")


def show_status(args):
    """Show all jobs."""
    for job_file in sorted(JOBS_DIR.glob("*.json")):
        info = json.loads(job_file.read_text())
        print(f"  {info['job_id']:40s} {info.get('status', '?'):12s} {info.get('gpu', '?')}")


def recover_job(args):
    """Reconnect to a detached job."""
    from r2_manager import R2Manager
    import vastai_manager as vast

    config = load_config()
    job_path = JOBS_DIR / f"{args.job_id}.json"
    if not job_path.exists():
        print(f"Job not found: {args.job_id}")
        return

    info = json.loads(job_path.read_text())
    r2 = R2Manager(config["r2"])
    bucket = info.get("r2_bucket", "")

    # Check if already done
    done = r2.get_done(bucket)
    if done:
        print(f"Job already done: {done.get('status')}")
        downloaded = r2.download_results(bucket, info.get("local_results", "./results/"))
        print(f"Downloaded {len(downloaded)} files")
        r2.delete_bucket(bucket)
        if info.get("instance_id"):
            vast.destroy_instance(info["instance_id"])
        return

    # Resume monitoring
    instance_id = info.get("instance_id")
    print(f"Reconnecting to {args.job_id} (instance={instance_id})...")
    monitor_job(r2, bucket, args.job_id, instance_id, 2)


def cleanup_job(args):
    """Force cleanup a job."""
    from r2_manager import R2Manager
    import vastai_manager as vast

    config = load_config()
    job_path = JOBS_DIR / f"{args.job_id}.json"

    if job_path.exists():
        info = json.loads(job_path.read_text())
        r2 = R2Manager(config["r2"])
        if info.get("r2_bucket"):
            r2.delete_bucket(info["r2_bucket"])
            print(f"  Deleted bucket: {info['r2_bucket']}")
        if info.get("instance_id"):
            vast.destroy_instance(info["instance_id"])
            print(f"  Destroyed instance: {info['instance_id']}")
        info["status"] = "cleaned"
        job_path.write_text(json.dumps(info, indent=2))
    else:
        print(f"Job not found: {args.job_id}")


def rerun_experiment(args):
    """Run a new experiment on an existing instance (skips boot, pip install cached)."""
    from r2_manager import R2Manager
    import vastai_manager as vast
    import subprocess as sp

    config = load_config()
    instance_id = int(args.instance_id)
    job_id = generate_job_id(args.name or "rerun")

    print(f"\n{'='*60}")
    print(f"  GPU2Vast RERUN: {job_id}")
    print(f"  Instance: {instance_id} (reusing)")
    print(f"  Script: {args.script}")
    print(f"{'='*60}\n")

    # Verify instance is alive
    if not vast.is_instance_alive(instance_id):
        print(f"  ERROR: Instance {instance_id} is not running")
        return

    conn = vast.get_connection_info(instance_id)
    ssh_host = conn.get("ssh_host", "")
    ssh_port = conn.get("ssh_port", "")
    key_path = KEYS_DIR / "ssh" / "gpu2vast_ed25519"

    if not ssh_host or not key_path.exists():
        print(f"  ERROR: Cannot SSH to instance (host={ssh_host}, key={key_path.exists()})")
        return

    r2 = R2Manager(config["r2"])
    bucket = r2.create_bucket(job_id)

    try:
        # Upload new data
        print("[1/4] Uploading new data...")
        r2.upload_files(bucket, args.data)
        print("  Upload complete")

        # Copy data to instance via SSH + R2
        print("[2/4] Downloading data to instance...")
        r2_endpoint = f"https://{config['r2']['account_id']}.r2.cloudflarestorage.com"
        download_cmd = (
            f"python3 -c \""
            f"import boto3,os; "
            f"s3=boto3.client('s3',endpoint_url='{r2_endpoint}',"
            f"aws_access_key_id='{config['r2']['access_key']}',"
            f"aws_secret_access_key='{config['r2']['secret_key']}',"
            f"region_name='auto'); "
            f"os.makedirs('/workspace/data',exist_ok=True); "
            f"[s3.download_file('{bucket}',o['Key'],'/workspace/data/'+o['Key'].split('/')[-1]) "
            f"for p in s3.get_paginator('list_objects_v2').paginate(Bucket='{bucket}',Prefix='data/') "
            f"for o in p.get('Contents',[])]; "
            f"print('Downloaded')\""
        )
        result = sp.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
             "-i", str(key_path), "-p", str(ssh_port), f"root@{ssh_host}",
             download_cmd],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            print(f"  ERROR: Data download failed: {result.stderr[:200]}")
            r2.delete_bucket(bucket)
            return
        print(f"  Data ready on instance")

        # Run the script via SSH
        print(f"[3/4] Running: {args.script}")
        run_cmd = (
            f"cd /workspace/data && "
            f"rm -rf results/ runs/ 2>/dev/null; "
            f"mkdir -p runs && "
            f"nohup tensorboard --logdir=runs --host=0.0.0.0 --port=6006 > /dev/null 2>&1 & "
            f"{args.script} 2>&1 | tee /workspace/stdout.log; "
            f"EXIT_CODE=$?; "
            f"python3 -c \""
            f"import boto3,json,glob,time; from pathlib import Path; "
            f"s3=boto3.client('s3',endpoint_url='{r2_endpoint}',"
            f"aws_access_key_id='{config['r2']['access_key']}',"
            f"aws_secret_access_key='{config['r2']['secret_key']}',"
            f"region_name='auto'); "
            f"[s3.upload_file(fp,'{bucket}','results/'+Path(fp).name) "
            f"for fp in glob.glob('results/**/*',recursive=True) if Path(fp).is_file()]; "
            f"s3.upload_file('/workspace/stdout.log','{bucket}','logs/stdout.log'); "
            f"s3.put_object(Bucket='{bucket}',Key='done.json',"
            f"Body=json.dumps({{'status':'success','ts':time.time()}})); "
            f"print('Uploaded')\""
        )

        # Stream output via SSH (blocking, shows real-time output)
        proc = sp.Popen(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
             "-i", str(key_path), "-p", str(ssh_port), f"root@{ssh_host}",
             run_cmd],
            stdout=sp.PIPE, stderr=sp.STDOUT, text=True,
        )
        for line in proc.stdout:
            _safe_print(f"  [run] {line.rstrip()}")
        proc.wait()

        # Download results
        print(f"\n[4/4] Downloading results...")
        downloaded = r2.download_results(bucket, args.local_results)
        print(f"  Downloaded {len(downloaded)} files to {args.local_results}")

        print(f"\n{'='*60}")
        print(f"  RERUN COMPLETE: {job_id}")
        print(f"  Instance {instance_id} still alive (use cleanup to destroy)")
        print(f"{'='*60}")

    finally:
        r2.delete_bucket(bucket)


def cleanup_all(args):
    """Clean all orphaned R2 buckets and vast.ai instances."""
    from r2_manager import R2Manager
    import vastai_manager as vast

    config = load_config()
    r2 = R2Manager(config["r2"])

    buckets = r2.list_buckets()
    print(f"GPU2Vast buckets: {len(buckets)}")
    for b in buckets:
        r2.delete_bucket(b)
        print(f"  Deleted: {b}")

    instances = vast.list_instances()
    if isinstance(instances, list):
        for inst in instances:
            vast.destroy_instance(inst["id"])
            print(f"  Destroyed instance: {inst['id']}")


def main():
    parser = argparse.ArgumentParser(description="GPU2Vast: Run GPU experiments on vast.ai")
    sub = parser.add_subparsers(dest="command")

    # run
    run_p = sub.add_parser("run", help="Run experiment")
    run_p.add_argument("--script", required=True, help="Command to run")
    run_p.add_argument("--data", nargs="+", required=True, help="Files to upload")
    run_p.add_argument("--name", default="experiment", help="Job name")
    run_p.add_argument("--gpu", default="RTX_4090", help="GPU type")
    run_p.add_argument("--max-price", type=float, default=0.50, help="Max $/hr")
    run_p.add_argument("--max-hours", type=float, default=2, help="Max runtime hours")
    run_p.add_argument("--disk", type=int, default=30, help="Disk GB")
    run_p.add_argument("--image", default="auto",
                        help="Docker image ('auto' selects based on script imports)")
    run_p.add_argument("--spot", action="store_true",
                        help="Use spot/interruptible instances (50-70%% cheaper)")
    run_p.add_argument("--keep-alive", action="store_true",
                        help="Keep instance alive after job (for rerun)")
    run_p.add_argument("--results-pattern", default="results/*")
    run_p.add_argument("--local-results", default="./results/")
    run_p.set_defaults(func=run_experiment)

    # rerun
    rerun_p = sub.add_parser("rerun", help="Run new experiment on existing instance")
    rerun_p.add_argument("--instance-id", required=True, help="Instance ID from previous --keep-alive run")
    rerun_p.add_argument("--script", required=True, help="Command to run")
    rerun_p.add_argument("--data", nargs="+", required=True, help="Files to upload")
    rerun_p.add_argument("--name", default="rerun", help="Job name")
    rerun_p.add_argument("--local-results", default="./results/")
    rerun_p.set_defaults(func=rerun_experiment)

    # status
    status_p = sub.add_parser("status", help="Show all jobs")
    status_p.set_defaults(func=show_status)

    # recover
    recover_p = sub.add_parser("recover", help="Reconnect to detached job")
    recover_p.add_argument("--job-id", required=True)
    recover_p.set_defaults(func=recover_job)

    # cleanup
    clean_p = sub.add_parser("cleanup", help="Force cleanup a job")
    clean_p.add_argument("--job-id", required=True)
    clean_p.set_defaults(func=cleanup_job)

    # cleanup-all
    cleanall_p = sub.add_parser("cleanup-all", help="Clean all orphaned resources")
    cleanall_p.set_defaults(func=cleanup_all)

    args = parser.parse_args()
    if args.command:
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
