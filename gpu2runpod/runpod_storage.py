"""
RunPod Storage Manager: S3-compatible storage using RunPod Network Volumes.

RunPod's S3 API uses Network Volume IDs as bucket names.
Each job gets an isolated prefix: {volume_id}/{job_id}/data/ and {job_id}/results/
No bucket creation/deletion needed — volume is pre-provisioned.

Config (keys/runpod_storage.key as JSON):
  {
    "endpoint":   "https://s3api-us-ks-2.runpod.io/",
    "access_key": "user_...",
    "secret_key": "rps_...",
    "volume_id":  "xxxxxxxx"
  }

Available endpoints by datacenter:
  EUR-IS-1: https://s3api-eur-is-1.runpod.io/
  EU-RO-1:  https://s3api-eu-ro-1.runpod.io/
  EU-CZ-1:  https://s3api-eu-cz-1.runpod.io/
  US-KS-2:  https://s3api-us-ks-2.runpod.io/  (default)
"""

import hashlib
import json
import time
from pathlib import Path

import boto3
from botocore.config import Config


class RunPodStorage:
    def __init__(self, config: dict):
        self.volume_id = config["volume_id"]
        self.endpoint = config.get("endpoint", "https://s3api-us-ks-2.runpod.io/")
        # Region is the datacenter slug embedded in the endpoint hostname
        # e.g. s3api-us-ks-2.runpod.io -> us-ks-2
        import re as _re
        m = _re.search(r"s3api-([a-z0-9-]+)\.runpod\.io", self.endpoint)
        region = m.group(1) if m else "us-ks-2"
        self.s3 = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=config["access_key"],
            aws_secret_access_key=config["secret_key"],
            region_name=region,
            config=Config(
                retries={"max_attempts": 5},
                read_timeout=3600,
                connect_timeout=30,
                s3={"addressing_style": "path"},
            ),
        )

    def _list_all(self, prefix: str, max_objects: int = 50000) -> list:
        """Manual pagination that handles duplicate-token bugs in RunPod S3."""
        result = []
        token = None
        seen = set()
        while True:
            kwargs = {"Bucket": self.volume_id, "Prefix": prefix, "MaxKeys": 1000}
            if token:
                kwargs["ContinuationToken"] = token
            resp = self.s3.list_objects_v2(**kwargs)
            result.extend(resp.get("Contents", []))
            if not resp.get("IsTruncated"):
                break
            next_token = resp.get("NextContinuationToken")
            if not next_token or next_token in seen:
                break
            seen.add(next_token)
            token = next_token
            if len(result) >= max_objects:
                break
        return result

    def create_bucket(self, job_id: str) -> str:
        """Return the job prefix (no actual bucket creation needed).

        'Bucket' = volume_id, 'prefix namespace' = job_id/.
        Returns the job_id prefix string used by all other methods.
        """
        print(f"  [runpod-storage] Volume: {self.volume_id}, Job prefix: {job_id}/")
        # Verify volume is accessible
        try:
            self.s3.list_objects_v2(Bucket=self.volume_id, Prefix=f"{job_id}/", MaxKeys=1)
            print(f"  [runpod-storage] Volume accessible")
        except Exception as e:
            raise RuntimeError(f"Cannot access RunPod volume {self.volume_id}: {e}")
        return job_id

    def upload_files(self, job_id: str, files: list[str], prefix: str = "data/",
                     parallel: bool = True):
        """Upload files to {volume_id}/{job_id}/{prefix}{filename}.

        Supports rename syntax: 'local_path:remote_name'.
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

        def _upload_one(item):
            local_path, remote_name = item
            key = f"{job_id}/{prefix}{remote_name}"
            md5 = hashlib.md5(local_path.read_bytes()).hexdigest()
            self.s3.upload_file(str(local_path), self.volume_id, key)
            return key, {"size": local_path.stat().st_size, "md5": md5}

        if parallel and len(valid_files) > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            failed = []
            with ThreadPoolExecutor(max_workers=min(4, len(valid_files))) as pool:
                futures = {pool.submit(_upload_one, item): item for item in valid_files}
                for future in as_completed(futures):
                    item = futures[future]
                    try:
                        key, info = future.result()
                        manifest[key] = info
                        print(f"  Uploaded: {Path(key).name} ({info['size']:,} bytes)")
                    except Exception as e:
                        failed.append((item, e))
                        print(f"  FAILED: {item[1]}: {e}")

            if failed:
                print(f"  Retrying {len(failed)} failed uploads...")
                for item, _ in failed:
                    try:
                        key, info = _upload_one(item)
                        manifest[key] = info
                        print(f"  Uploaded (retry): {item[1]}")
                    except Exception as e2:
                        raise RuntimeError(f"Upload failed after retry: {item[1]}: {e2}")
        else:
            for local_path, remote_name in valid_files:
                key, info = _upload_one((local_path, remote_name))
                manifest[key] = info
                print(f"  Uploaded: {remote_name} ({info['size']:,} bytes)")

        # Merge with any existing manifest (multiple upload_files calls accumulate)
        existing = {}
        try:
            resp = self.s3.get_object(Bucket=self.volume_id, Key=f"{job_id}/manifest.json")
            existing = json.loads(resp["Body"].read())
        except Exception:
            pass
        merged = {**existing, **manifest}
        self.s3.put_object(
            Bucket=self.volume_id,
            Key=f"{job_id}/manifest.json",
            Body=json.dumps(merged, indent=2),
        )
        return manifest

    def upload_config(self, job_id: str, config: dict):
        """Upload job configuration."""
        self.s3.put_object(
            Bucket=self.volume_id,
            Key=f"{job_id}/job_config.json",
            Body=json.dumps(config, indent=2),
        )

    def download_results(self, job_id: str, local_dir: str, sub_prefix: str = "results/",
                         parallel: bool = True, manifest_keys: list[str] | None = None):
        """Download results from {volume_id}/{job_id}/{sub_prefix} to local_dir.

        manifest_keys: explicit list of S3 keys to download (bypasses list_objects_v2,
        which is broken on RunPod S3 — always returns empty). When None, tries listing
        then falls back to done.json file list.
        """
        prefix = f"{job_id}/{sub_prefix}"
        print(f"  [runpod-storage] Downloading {prefix} to {local_dir}")
        Path(local_dir).mkdir(parents=True, exist_ok=True)

        to_download = []

        if manifest_keys is not None:
            for key in manifest_keys:
                filename = key.replace(prefix, "", 1).lstrip("/")
                if not filename:
                    continue
                local_path = Path(local_dir) / filename
                local_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    head = self.s3.head_object(Bucket=self.volume_id, Key=key)
                    size = head["ContentLength"]
                except Exception:
                    size = 0
                to_download.append((key, str(local_path), size))
        else:
            objects = self._list_all(prefix)
            if not objects:
                # RunPod S3 list_objects_v2 is broken — try done.json for file manifest
                try:
                    done = self.get_done(job_id)
                    if done and done.get("files"):
                        for key, info in done["files"].items():
                            if f"/{sub_prefix}" not in key and not key.startswith(prefix):
                                continue
                            filename = key.replace(prefix, "", 1).lstrip("/")
                            if not filename:
                                continue
                            local_path = Path(local_dir) / filename
                            local_path.parent.mkdir(parents=True, exist_ok=True)
                            to_download.append((key, str(local_path), info.get("size", 0)))
                        print(f"  [runpod-storage] Using done.json manifest ({len(to_download)} files)")
                except Exception:
                    pass
            else:
                for obj in objects:
                    key = obj["Key"]
                    filename = key.replace(prefix, "", 1)
                    if not filename:
                        continue
                    local_path = Path(local_dir) / filename
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    to_download.append((key, str(local_path), obj["Size"]))

        downloaded = []

        def _dl(item):
            key, local_path, size = item
            self.s3.download_file(self.volume_id, key, local_path)
            actual = Path(local_path).stat().st_size
            if actual != size:
                raise IOError(f"size mismatch for {key}: expected {size}, got {actual}")
            return local_path, Path(key).name, size

        if parallel and len(to_download) > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            failed = []
            with ThreadPoolExecutor(max_workers=min(4, len(to_download))) as pool:
                futures = {pool.submit(_dl, item): item for item in to_download}
                for future in as_completed(futures):
                    item = futures[future]
                    try:
                        local_path, name, size = future.result()
                        print(f"  [runpod-storage] Downloaded: {name} ({size:,} bytes)")
                        downloaded.append(local_path)
                    except Exception as e:
                        failed.append(item)
                        print(f"  [runpod-storage] FAILED: {Path(item[0]).name}: {e}")

            for item in failed:
                try:
                    local_path, name, size = _dl(item)
                    print(f"  [runpod-storage] Downloaded (retry): {name}")
                    downloaded.append(local_path)
                except Exception as e2:
                    print(f"  [runpod-storage] Download failed: {Path(item[0]).name}: {e2}")
        else:
            for item in to_download:
                try:
                    local_path, name, size = _dl(item)
                    print(f"  [runpod-storage] Downloaded: {name} ({size:,} bytes)")
                    downloaded.append(local_path)
                except Exception as e:
                    print(f"  [runpod-storage] FAILED: {Path(item[0]).name}: {e}")

        print(f"  [runpod-storage] Downloaded {len(downloaded)} result files")
        return downloaded

    def get_progress(self, job_id: str) -> dict | None:
        try:
            resp = self.s3.get_object(Bucket=self.volume_id, Key=f"{job_id}/progress.json")
            return json.loads(resp["Body"].read())
        except Exception:
            return None

    def get_done(self, job_id: str) -> dict | None:
        try:
            resp = self.s3.get_object(Bucket=self.volume_id, Key=f"{job_id}/done.json")
            return json.loads(resp["Body"].read())
        except Exception:
            return None

    def get_error(self, job_id: str) -> dict | None:
        try:
            resp = self.s3.get_object(Bucket=self.volume_id, Key=f"{job_id}/error.json")
            return json.loads(resp["Body"].read())
        except Exception:
            return None

    def _collect_job_keys(self, job_id: str) -> list[str]:
        """Collect all S3 keys for a job, working around broken list_objects_v2."""
        key_set: set[str] = set()

        # Try listing (may return empty on RunPod S3)
        for obj in self._list_all(f"{job_id}/"):
            key_set.add(obj["Key"])

        if not key_set:
            # Listing broken — reconstruct from manifest + done.json + standard keys
            try:
                resp = self.s3.get_object(Bucket=self.volume_id, Key=f"{job_id}/manifest.json")
                manifest = json.loads(resp["Body"].read())
                key_set.update(manifest.keys())
                key_set.add(f"{job_id}/manifest.json")
            except Exception:
                pass
            try:
                done = self.get_done(job_id)
                if done and done.get("files"):
                    key_set.update(done["files"].keys())
            except Exception:
                pass
            for suffix in [
                "job_config.json", "manifest.json", "progress.json", "done.json",
                "error.json", "gpu_metrics.json", "logs/stdout.log",
            ]:
                key_set.add(f"{job_id}/{suffix}")

        # Filter to only keys that actually exist (head_object confirms)
        confirmed = []
        for key in key_set:
            try:
                self.s3.head_object(Bucket=self.volume_id, Key=key)
                confirmed.append(key)
            except Exception:
                pass
        return confirmed

    def delete_job(self, job_id: str):
        """Delete all objects under {volume_id}/{job_id}/."""
        print(f"  [runpod-storage] Deleting job prefix: {job_id}/")
        try:
            keys = self._collect_job_keys(job_id)
            count = 0
            all_keys = [{"Key": k} for k in keys]
            for i in range(0, len(all_keys), 1000):
                batch = all_keys[i:i + 1000]
                try:
                    self.s3.delete_objects(Bucket=self.volume_id, Delete={"Objects": batch})
                    count += len(batch)
                except Exception:
                    for item in batch:
                        try:
                            self.s3.delete_object(Bucket=self.volume_id, Key=item["Key"])
                            count += 1
                        except Exception:
                            pass
            print(f"  [runpod-storage] Deleted {count} objects for job {job_id}")
        except Exception as e:
            print(f"  [runpod-storage] Warning: cleanup error: {e}")

    # Alias for compatibility with cleanup code that calls delete_bucket(bucket)
    def delete_bucket(self, job_id: str):
        self.delete_job(job_id)

    def list_jobs(self) -> list[str]:
        """List all gpu2runpod job prefixes in the volume."""
        try:
            resp = self.s3.list_objects_v2(
                Bucket=self.volume_id, Delimiter="/", MaxKeys=200
            )
            prefixes = [
                p["Prefix"].rstrip("/")
                for p in resp.get("CommonPrefixes", [])
            ]
            return prefixes
        except Exception:
            return []
