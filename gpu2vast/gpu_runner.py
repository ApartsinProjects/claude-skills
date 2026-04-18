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

    print(f"\n{'='*60}")
    print(f"  GPU2Vast: {job_id}")
    print(f"  Script: {args.script}")
    print(f"  GPU: {args.gpu}, Max: ${args.max_price}/hr")
    print(f"{'='*60}\n")

    # Save job info
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

    try:
        # 1. Create R2 bucket
        print("[1/6] Creating R2 bucket...")
        r2 = R2Manager(config["r2"])
        bucket = r2.create_bucket(job_id)
        job_info["r2_bucket"] = bucket
        print(f"  Bucket: {bucket}")

        # 2. Upload data + onstart script
        print("[2/6] Uploading data...")
        r2.upload_files(bucket, args.data)

        # Upload the onstart script
        onstart_path = SKILL_DIR / "container" / "onstart.sh"
        r2.upload_files(bucket, [str(onstart_path)], prefix="")

        r2.upload_config(bucket, {
            "experiment_cmd": args.script,
            "results_pattern": args.results_pattern,
            "job_id": job_id,
        })

        # 3. Find GPU
        print(f"[3/6] Searching for {args.gpu} <= ${args.max_price}/hr...")
        offers = vast.search_gpu(
            gpu_name=args.gpu, max_price=args.max_price, disk_gb=args.disk,
        )
        if not offers:
            print("  No matching GPU found!")
            raise RuntimeError("No GPU available")
        offer = offers[0]
        print(f"  Found: {offer.get('gpu_name')} @ ${offer.get('dph_total', '?')}/hr (id={offer['id']})")

        # 4. Launch instance
        print("[4/6] Launching instance...")
        # Load HF token if available
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
        job_info["status"] = "running"
        job_path.write_text(json.dumps(job_info, indent=2))
        print(f"  Instance: {instance_id}")

        # 5. Monitor via R2
        print("[5/6] Monitoring (Ctrl+C to detach, use --recover to reconnect)...")
        monitor_job(r2, bucket, job_id, args.max_hours)

        # 6. Download results
        print("[6/6] Downloading results...")
        downloaded = r2.download_results(bucket, args.local_results)
        print(f"  Downloaded {len(downloaded)} files to {args.local_results}")

        # Cleanup
        print("\nCleaning up...")
        if instance_id:
            vast.destroy_instance(instance_id)
            print(f"  Destroyed instance {instance_id}")
        r2.delete_bucket(bucket)
        print(f"  Deleted R2 bucket {bucket}")

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

    except Exception as e:
        print(f"\n  Error: {e}")
        job_info["status"] = "failed"
        job_info["error"] = str(e)
        job_path.write_text(json.dumps(job_info, indent=2))
        # Attempt cleanup
        try:
            if job_info.get("instance_id"):
                vast.destroy_instance(job_info["instance_id"])
            if job_info.get("r2_bucket"):
                r2.delete_bucket(job_info["r2_bucket"])
        except:
            pass


def monitor_job(r2, bucket, job_id, max_hours):
    """Poll R2 for progress until done or timeout."""
    start = time.time()
    max_seconds = max_hours * 3600
    stale_count = 0

    while True:
        elapsed = time.time() - start
        if elapsed > max_seconds:
            print(f"\n  TIMEOUT after {max_hours}h")
            break

        # Check done
        done = r2.get_done(bucket)
        if done:
            status = done.get("status", "unknown")
            print(f"\n  Job finished: {status}")
            return

        # Check error
        error = r2.get_error(bucket)
        if error:
            print(f"\n  Job error: {error}")
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
            if stale_count > 20:
                print(f"\n  No progress for {stale_count * 30}s, may have failed")

        time.sleep(30)


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
    print(f"Reconnecting to {args.job_id}...")
    monitor_job(r2, bucket, args.job_id, 2)


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
