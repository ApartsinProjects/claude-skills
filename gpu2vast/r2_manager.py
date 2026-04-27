"""
Cloudflare R2 Manager: Ephemeral bucket lifecycle.
Create, upload, download, delete buckets per job.
"""

import boto3
import json
import hashlib
from pathlib import Path
from boto3.s3.transfer import TransferConfig

# Tuned for >300 MB single-PUT 524s: multipart at 64 MB, 32 MB chunks, 8 threads.
_TRANSFER_CONFIG = TransferConfig(
    multipart_threshold=64 * 1024 * 1024,
    multipart_chunksize=32 * 1024 * 1024,
    max_concurrency=8,
    use_threads=True,
)


def _stream_md5(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute md5 by streaming chunks (avoids loading whole file into RAM)."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _upload_one_aware(s3, local_path: Path, bucket: str, key: str):
    """Upload with CRLF stripping for .sh files + streaming md5 + TransferConfig."""
    md5 = _stream_md5(local_path)
    if str(local_path).lower().endswith(".sh"):
        raw = local_path.read_bytes()
        cleaned = raw.replace(b"\r\n", b"\n")
        s3.put_object(Bucket=bucket, Key=key, Body=cleaned)
        size = len(cleaned)
    else:
        s3.upload_file(str(local_path), bucket, key, Config=_TRANSFER_CONFIG)
        size = local_path.stat().st_size
    return md5, size


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
        print(f"  [r2] Creating bucket: {bucket}")
        self.s3.create_bucket(Bucket=bucket)
        print(f"  [r2] Bucket created")
        return bucket

    def upload_files(self, bucket: str, files: list[str], prefix: str = "data/",
                     parallel: bool = True):
        """Upload local files to R2 bucket. Uses parallel uploads for speed.

        Files can use rename syntax: 'local_path:remote_name' to upload
        local_path as remote_name (e.g. 'my_train.py:train.py').
        """
        manifest = {}
        valid_files = []
        for filepath in files:
            if ":" in filepath and not Path(filepath).exists():
                parts = filepath.rsplit(":", 1)
                local_path = Path(parts[0])
                remote_name = parts[1]
            else:
                local_path = Path(filepath)
                remote_name = local_path.name
            if not local_path.exists():
                print(f"  SKIP (not found): {filepath}")
                continue
            valid_files.append((local_path, remote_name))

        if parallel and len(valid_files) > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def _upload_one(item):
                local_path, remote_name = item
                key = prefix + remote_name
                md5, size = _upload_one_aware(self.s3, local_path, bucket, key)
                return key, {"size": size, "md5": md5}

            failed_uploads = []
            with ThreadPoolExecutor(max_workers=min(8, len(valid_files))) as pool:
                futures = {pool.submit(_upload_one, item): item for item in valid_files}
                for future in as_completed(futures):
                    item = futures[future]
                    try:
                        key, info = future.result()
                        manifest[key] = info
                        print(f"  Uploaded: {Path(key).name} ({info['size']:,} bytes)")
                    except Exception as e:
                        failed_uploads.append((item, e))
                        print(f"  FAILED: {item[1]}: {e}")

            if failed_uploads:
                print(f"  Retrying {len(failed_uploads)} failed uploads...")
                for item, _ in failed_uploads:
                    try:
                        local_path, remote_name = item
                        key = prefix + remote_name
                        md5, size = _upload_one_aware(self.s3, local_path, bucket, key)
                        manifest[key] = {"size": size, "md5": md5}
                        print(f"  Uploaded (retry): {remote_name}")
                    except Exception as e2:
                        raise RuntimeError(f"Upload failed after retry: {item[1]}: {e2}")
        else:
            for local_path, remote_name in valid_files:
                key = prefix + remote_name
                md5, size = _upload_one_aware(self.s3, local_path, bucket, key)
                manifest[key] = {"size": size, "md5": md5}
                print(f"  Uploaded: {remote_name} ({size:,} bytes)")

        self.s3.put_object(
            Bucket=bucket, Key="manifest.json",
            Body=json.dumps(manifest, indent=2),
        )
        return manifest

    def upload_config(self, bucket: str, config: dict):
        """Upload job configuration."""
        print(f"  [r2] Uploading job config to {bucket}")
        self.s3.put_object(
            Bucket=bucket, Key="job_config.json",
            Body=json.dumps(config, indent=2),
        )
        print(f"  [r2] Config uploaded")

    def download_results(self, bucket: str, local_dir: str, prefix: str = "results/",
                         parallel: bool = True):
        """Download all results from R2 to local directory. Uses parallel downloads."""
        print(f"  [r2] Downloading results from {bucket}/{prefix} to {local_dir}")
        Path(local_dir).mkdir(parents=True, exist_ok=True)

        # Collect all objects first
        to_download = []
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                filename = key.replace(prefix, "", 1)
                if not filename:
                    continue
                local_path = Path(local_dir) / filename
                local_path.parent.mkdir(parents=True, exist_ok=True)
                to_download.append((key, str(local_path), obj["Size"]))

        downloaded = []
        if parallel and len(to_download) > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def _download_one(item):
                key, local_path, size = item
                self.s3.download_file(bucket, key, local_path, Config=_TRANSFER_CONFIG)
                actual = Path(local_path).stat().st_size
                if actual != size:
                    raise IOError(f"size mismatch for {key}: expected {size}, got {actual}")
                return local_path, Path(key).name, size

            failed_downloads = []
            with ThreadPoolExecutor(max_workers=min(8, len(to_download))) as pool:
                futures = {pool.submit(_download_one, item): item for item in to_download}
                for future in as_completed(futures):
                    item = futures[future]
                    try:
                        local_path, name, size = future.result()
                        print(f"  [r2] Downloaded: {name} ({size:,} bytes)")
                        downloaded.append(local_path)
                    except Exception as e:
                        failed_downloads.append(item)
                        print(f"  [r2] FAILED: {Path(item[0]).name}: {e}")

            for item in failed_downloads:
                try:
                    key, local_path, size = item
                    self.s3.download_file(bucket, key, local_path, Config=_TRANSFER_CONFIG)
                    print(f"  [r2] Downloaded (retry): {Path(key).name}")
                    downloaded.append(local_path)
                except Exception as e2:
                    print(f"  [r2] Download failed after retry: {Path(item[0]).name}: {e2}")
        else:
            for key, local_path, size in to_download:
                self.s3.download_file(bucket, key, local_path, Config=_TRANSFER_CONFIG)
                actual = Path(local_path).stat().st_size
                if actual != size:
                    raise IOError(f"size mismatch for {key}: expected {size}, got {actual}")
                print(f"  [r2] Downloaded: {Path(key).name} ({size:,} bytes)")
                downloaded.append(local_path)

        print(f"  [r2] Downloaded {len(downloaded)} result files")
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
        """Delete all objects and the bucket itself. Handles >1000 objects."""
        print(f"  [r2] Deleting bucket: {bucket}")
        try:
            paginator = self.s3.get_paginator("list_objects_v2")
            obj_count = 0
            for page in paginator.paginate(Bucket=bucket):
                all_keys = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
                # delete_objects accepts max 1000 keys per call
                for i in range(0, len(all_keys), 1000):
                    batch = all_keys[i:i + 1000]
                    self.s3.delete_objects(Bucket=bucket, Delete={"Objects": batch})
                    obj_count += len(batch)
            self.s3.delete_bucket(Bucket=bucket)
            print(f"  [r2] Deleted bucket {bucket} ({obj_count} objects removed)")
        except Exception as e:
            print(f"  [r2] Warning: bucket cleanup error: {e}")

    def list_buckets(self) -> list[str]:
        """List all gpu2vast buckets."""
        resp = self.s3.list_buckets()
        return [b["Name"] for b in resp.get("Buckets", []) if b["Name"].startswith("gpu2vast-")]
