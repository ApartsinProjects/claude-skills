"""Detect orphan RunPod pods (live pods not tracked in jobs/*.json).

Usage:
    python orphans.py            # list orphans, with cost burned and SSH hint
    python orphans.py --cleanup  # terminate every orphan (asks per-pod)

Orphans typically come from:
    - manual pod creation outside the runner
    - jobs whose JSON was deleted/corrupted
    - skill version upgrades that changed the JSON schema
    - cleanup paths that didn't run to completion
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
import requests

HERE = Path(__file__).parent
KEY = (HERE / "keys" / "runpod.key").read_text().strip()
JOBS_DIR = HERE / "jobs"
API = "https://rest.runpod.io/v1"


def tracked_pod_ids():
    ids = set()
    for f in JOBS_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text())
            pid = d.get("pod_id")
            if pid:
                ids.add(pid)
        except Exception:
            pass
    return ids


def list_pods():
    r = requests.get(f"{API}/pods", headers={"Authorization": f"Bearer {KEY}"})
    r.raise_for_status()
    return r.json()


def hours_since(iso):
    if not iso: return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00").rstrip(" UTC"))
    except Exception:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cleanup", action="store_true",
                    help="Terminate every orphan (prompts per pod)")
    args = ap.parse_args()

    tracked = tracked_pod_ids()
    pods = list_pods()
    orphans = [p for p in pods if p.get("id") not in tracked]

    if not orphans:
        print(f"[orphans] {len(pods)} live pods, all tracked. No orphans.")
        return

    print(f"[orphans] {len(orphans)} orphan pod(s) (of {len(pods)} live):\n")
    print(f"{'ID':<18} {'Status':<10} {'GPU':<14} {'$/hr':>6} {'Hours':>6} {'Burned':>8}  Image")
    print("-" * 110)
    total_burned = 0.0
    for p in orphans:
        pid = p.get("id")
        status = p.get("desiredStatus", "?")
        gpu = (p.get("machine") or {}).get("gpuTypeId") or "?"
        cost = p.get("costPerHr") or 0
        hrs = hours_since(p.get("lastStartedAt", ""))
        burned = (cost * hrs) if (cost and hrs) else 0
        total_burned += burned
        img = (p.get("imageName") or "")[:40]
        print(f"{pid:<18} {status:<10} {gpu:<14} {cost:>6.3f} "
              f"{(hrs or 0):>6.1f} {burned:>7.2f}$  {img}")

    print(f"\n[orphans] Total burned (running orphans): ${total_burned:.2f}")
    print(f"\n[orphans] Cleanup any of them with:")
    for p in orphans:
        print(f"  python orphans.py --cleanup       # interactive")
        print(f"  curl -X DELETE {API}/pods/{p['id']} -H 'Authorization: Bearer $KEY'")
        break

    if args.cleanup:
        print()
        for p in orphans:
            ans = input(f"Terminate {p['id']} ({p.get('desiredStatus')}, "
                        f"{p.get('costPerHr',0):.3f}$/hr)? [y/N] ")
            if ans.strip().lower() == "y":
                r = requests.delete(f"{API}/pods/{p['id']}",
                                     headers={"Authorization": f"Bearer {KEY}"})
                print(f"  -> HTTP {r.status_code}")


if __name__ == "__main__":
    main()
