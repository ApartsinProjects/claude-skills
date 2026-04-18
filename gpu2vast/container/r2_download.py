"""Download experiment data from R2 bucket into /workspace/data/."""
import boto3, json, os
from pathlib import Path

WORKSPACE = Path("/workspace/data")
WORKSPACE.mkdir(parents=True, exist_ok=True)

s3 = boto3.client("s3",
    endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ["R2_ACCESS_KEY"],
    aws_secret_access_key=os.environ["R2_SECRET_KEY"],
    region_name="auto",
)
bucket = os.environ["R2_BUCKET"]

paginator = s3.get_paginator("list_objects_v2")
for page in paginator.paginate(Bucket=bucket, Prefix="data/"):
    for obj in page.get("Contents", []):
        key = obj["Key"]
        local = WORKSPACE / key.replace("data/", "", 1)
        local.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(bucket, key, str(local))
        print(f"  Downloaded: {key} ({obj['Size']:,} bytes)")
