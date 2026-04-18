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
import json
import os
import sys
import time
import yaml
from datetime import datetime
from pathlib import Path

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

        # 2. Upload data + onstart script
        print("[2/7] Uploading data...")
        r2.upload_files(bucket, args.data)
        onstart_path = SKILL_DIR / "container" / "onstart.sh"
        r2.upload_files(bucket, [str(onstart_path)], prefix="")
        r2.upload_config(bucket, {
            "experiment_cmd": args.script,
            "results_pattern": args.results_pattern,
            "job_id": job_id,
        })
        print("  Upload complete")

        # 3. Find GPU
        print(f"[3/7] Searching for {args.gpu} <= ${args.max_price}/hr...")
        offers = vast.search_gpu(
            gpu_name=args.gpu, max_price=args.max_price, disk_gb=args.disk,
        )
        if not offers:
            raise RuntimeError(f"No {args.gpu} available at <=${args.max_price}/hr")
        offer = offers[0]
        print(f"  Selected: {offer.get('gpu_name')} @ ${offer.get('dph_total', '?')}/hr (offer={offer['id']})")

        # 4. Launch instance
        print("[4/7] Launching instance...")
        hf_token = ""
        hf_key_file = KEYS_DIR / "huggingface.key"
        if hf_key_file.exists():
            hf_token = hf_key_file.read_text().strip()

        env_vars = {
            "R2_ACCOUNT_ID": config["r2"]["account_id"],
            "R2_ACCESS_KEY": config["r2"]["access_key"],
            "R2_SECRET_KEY": config["r2"]["secret_key"],
            "R2_BUCKET": bucket,
            "HF_TOKEN": hf_token,
            "JOB_ID": job_id,
            "EXPERIMENT_CMD": args.script,
            "RESULTS_PATTERN": args.results_pattern,
        }

        instance = vast.create_instance(
            offer_id=offer["id"],
            docker_image=args.image,
            env_vars=env_vars,
            disk_gb=args.disk,
        )
        instance_id = instance.get("new_contract") or instance.get("instance_id")
        job_info["instance_id"] = instance_id
        job_info["status"] = "booting"
        job_path.write_text(json.dumps(job_info, indent=2))

        # 5. Wait for instance to boot
        print("[5/7] Waiting for instance to boot...")
        if not vast.wait_for_running(instance_id, timeout=300):
            raise RuntimeError(f"Instance {instance_id} failed to boot within 300s")
        print(f"  Instance {instance_id} is running")
        job_info["status"] = "running"
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
        _cleanup(vast, r2, instance_id, bucket, job_info, job_path)


def _cleanup(vast, r2, instance_id, bucket, job_info, job_path):
    """Always destroy instance and delete bucket, regardless of outcome."""
    if job_info.get("status") == "detached":
        return
    print("\n  Cleaning up...")
    if instance_id:
        try:
            vast.destroy_instance(instance_id)
        except Exception as e:
            print(f"  [cleanup] Instance destroy failed: {e}")
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
                step = progress.get("step", "?")
                total = progress.get("total", "?")
                loss = progress.get("loss", "?")
                gpu_info = progress.get("gpu", {})
                gpu_util = gpu_info.get("gpu_util", "?")
                mins = elapsed / 60

                bar_pct = int(step) / int(total) * 100 if str(step).isdigit() and str(total).isdigit() else 0
                bar = "█" * int(bar_pct / 5) + "░" * (20 - int(bar_pct / 5))

                print(f"\r  {bar} {step}/{total}  loss={loss}  GPU={gpu_util}%  {mins:.0f}min  ", end="", flush=True)
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
    run_p.add_argument("--image", default="vastai/pytorch",
                        help="Docker image (vastai/pytorch is pre-cached on hosts)")
    run_p.add_argument("--results-pattern", default="results/*")
    run_p.add_argument("--local-results", default="./results/")
    run_p.set_defaults(func=run_experiment)

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
