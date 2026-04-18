"""
Cloudflare R2 Manager: Ephemeral bucket lifecycle.
Create, upload, download, delete buckets per job.
"""

import boto3
import json
import os
import hashlib
from pathlib import Path


class R2Manager:
    def __init__(self, config: dict):
        self.account_id = config["account_id"]
        self.endpoint = f"https://{self.account_id}.r2.cloudflarestorage.com"
        self.s3 = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=config["access_key"],
            aws_secret_access_key=config["secret_key"],
            region_name="auto",
        )

    def create_bucket(self, job_id: str) -> str:
        """Create ephemeral bucket for a job."""
        bucket = f"gpu2vast-{job_id}"
        self.s3.create_bucket(Bucket=bucket)
        return bucket

    def upload_files(self, bucket: str, files: list[str], prefix: str = "data/"):
        """Upload local files to R2 bucket."""
        manifest = {}
        for filepath in files:
            path = Path(filepath)
            if not path.exists():
                print(f"  SKIP (not found): {filepath}")
                continue
            key = prefix + path.name
            md5 = hashlib.md5(path.read_bytes()).hexdigest()
            self.s3.upload_file(str(path), bucket, key)
            manifest[key] = {"size": path.stat().st_size, "md5": md5}
            print(f"  Uploaded: {path.name} ({path.stat().st_size:,} bytes)")

        # Upload manifest
        self.s3.put_object(
            Bucket=bucket, Key="manifest.json",
            Body=json.dumps(manifest, indent=2),
        )
        return manifest

    def upload_config(self, bucket: str, config: dict):
        """Upload job configuration."""
        self.s3.put_object(
            Bucket=bucket, Key="job_config.json",
            Body=json.dumps(config, indent=2),
        )

    def download_results(self, bucket: str, local_dir: str, prefix: str = "results/"):
        """Download all results from R2 to local directory."""
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        downloaded = []

        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                filename = key.replace(prefix, "", 1)
                if not filename:
                    continue
                local_path = Path(local_dir) / filename
                local_path.parent.mkdir(parents=True, exist_ok=True)
                self.s3.download_file(bucket, key, str(local_path))
                downloaded.append(str(local_path))

        return downloaded

    def get_progress(self, bucket: str) -> dict | None:
        """Read progress.json from R2."""
        try:
            resp = self.s3.get_object(Bucket=bucket, Key="progress.json")
            return json.loads(resp["Body"].read())
        except Exception:
            return None

    def get_done(self, bucket: str) -> dict | None:
        """Read done.json from R2 (signals completion)."""
        try:
            resp = self.s3.get_object(Bucket=bucket, Key="done.json")
            return json.loads(resp["Body"].read())
        except Exception:
            return None

    def get_error(self, bucket: str) -> dict | None:
        """Read error.json from R2 (signals failure)."""
        try:
            resp = self.s3.get_object(Bucket=bucket, Key="error.json")
            return json.loads(resp["Body"].read())
        except Exception:
            return None

    def delete_bucket(self, bucket: str):
        """Delete all objects and the bucket itself."""
        try:
            paginator = self.s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket):
                objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
                if objects:
                    self.s3.delete_objects(Bucket=bucket, Delete={"Objects": objects})
            self.s3.delete_bucket(Bucket=bucket)
        except Exception as e:
            print(f"  Warning: bucket cleanup error: {e}")

    def list_buckets(self) -> list[str]:
        """List all gpu2vast buckets."""
        resp = self.s3.list_buckets()
        return [b["Name"] for b in resp.get("Buckets", []) if b["Name"].startswith("gpu2vast-")]
