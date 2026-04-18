"""Upload results + logs to R2 bucket, signal done."""
import boto3, json, os, hashlib, glob, sys, time
from pathlib import Path

s3 = boto3.client("s3",
    endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ["R2_ACCESS_KEY"],
    aws_secret_access_key=os.environ["R2_SECRET_KEY"],
    region_name="auto",
)
bucket = os.environ["R2_BUCKET"]
results_pattern = os.environ.get("RESULTS_PATTERN", "results/*")
exit_code = int(sys.argv[sys.argv.index("--exit-code") + 1]) if "--exit-code" in sys.argv else 0

# Upload results
uploaded = {}
for pattern in results_pattern.split(","):
    for filepath in glob.glob(pattern, recursive=True):
        path = Path(filepath)
        if path.is_file():
            key = f"results/{path.name}"
            md5 = hashlib.md5(path.read_bytes()).hexdigest()
            s3.upload_file(str(path), bucket, key)
            uploaded[key] = {"size": path.stat().st_size, "md5": md5}
            print(f"  Uploaded: {path.name} ({path.stat().st_size:,} bytes)")

# Upload stdout log
log_path = Path("/workspace/stdout.log")
if log_path.exists():
    s3.upload_file(str(log_path), bucket, "logs/stdout.log")

# Signal done
done = {
    "status": "success" if exit_code == 0 else "failed",
    "exit_code": exit_code,
    "files": uploaded,
    "timestamp": time.time(),
}
s3.put_object(Bucket=bucket, Key="done.json", Body=json.dumps(done, indent=2))
print(f"[GPU2Vast] Signaled done: {done['status']}")
