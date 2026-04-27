"""Detect orphan vast.ai instances (live instances not tracked in jobs/*.json).

Usage:
    python orphans.py            # list orphans, with cost burned and SSH hint
    python orphans.py --cleanup  # destroy every orphan (asks per-instance)

Orphans typically come from:
    - manual instance creation outside the runner
    - jobs whose JSON was deleted/corrupted
    - skill version upgrades that changed the JSON schema
    - cleanup paths that didn't run to completion
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
JOBS_DIR = HERE / "jobs"

sys.path.insert(0, str(HERE))


def tracked_instance_ids():
    ids = set()
    for f in JOBS_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text())
            iid = d.get("instance_id")
            if iid is not None:
                # vast.ai uses int IDs but JSON may store as int or string
                ids.add(int(iid))
        except Exception:
            pass
    return ids


def list_instances():
    import vastai_manager as vast
    raw = vast.list_instances()
    if isinstance(raw, dict):
        # Some vastai-cli versions wrap as {"instances": [...]}
        raw = raw.get("instances", [])
    return raw or []


def hours_since(iso):
    if not iso:
        return None
    try:
        if isinstance(iso, (int, float)):
            dt = datetime.fromtimestamp(float(iso), tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00").rstrip(" UTC"))
    except Exception:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cleanup", action="store_true",
                    help="Destroy every orphan (prompts per instance)")
    args = ap.parse_args()

    tracked = tracked_instance_ids()
    instances = list_instances()
    orphans = []
    for inst in instances:
        try:
            iid = int(inst.get("id"))
        except Exception:
            continue
        if iid not in tracked:
            orphans.append(inst)

    if not orphans:
        print(f"[orphans] {len(instances)} live instances, all tracked. No orphans.")
        return

    print(f"[orphans] {len(orphans)} orphan instance(s) (of {len(instances)} live):\n")
    print(f"{'ID':<12} {'Status':<12} {'GPU':<18} {'$/hr':>6} {'Hours':>6} {'Burned':>8}  Image")
    print("-" * 110)
    total_burned = 0.0
    for inst in orphans:
        iid = inst.get("id")
        status = inst.get("actual_status", inst.get("intended_status", "?"))
        gpu = inst.get("gpu_name", "?") or "?"
        cost = float(inst.get("dph_total") or 0)
        hrs = hours_since(inst.get("start_date") or inst.get("started_at"))
        burned = (cost * hrs) if (cost and hrs) else 0
        total_burned += burned
        img = (inst.get("image_uuid") or inst.get("image") or "")[:40]
        print(f"{iid!s:<12} {str(status):<12} {gpu:<18} {cost:>6.3f} "
              f"{(hrs or 0):>6.1f} {burned:>7.2f}$  {img}")

    print(f"\n[orphans] Total burned (running orphans): ${total_burned:.2f}")
    if not args.cleanup:
        print(f"\n[orphans] Cleanup: python orphans.py --cleanup       # interactive")
        return

    import vastai_manager as vast
    print()
    for inst in orphans:
        iid = inst.get("id")
        cost = float(inst.get("dph_total") or 0)
        ans = input(f"Destroy {iid} ({inst.get('actual_status','?')}, ${cost:.3f}/hr)? [y/N] ")
        if ans.strip().lower() == "y":
            try:
                vast.destroy_instance(int(iid))
                print(f"  -> destroyed")
            except Exception as e:
                print(f"  -> error: {e}")


if __name__ == "__main__":
    main()
