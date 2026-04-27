---
name: gpu2runpod
description: >
  Run any GPU-intensive PyTorch training, fine-tuning, encoding, or inference job
  on rented RunPod GPUs (RTX 4090, A100, H100, etc.) with RunPod S3-compatible
  Network Volume storage. Use when local GPU is too small/slow, when a job needs
  more VRAM than available locally (e.g. RTX 2060 6 GB), when the user explicitly
  asks to "run on RunPod", "use RunPod", "offload to RunPod", "use a bigger GPU",
  or "rent a GPU on RunPod". Fully automated provisioning, SSH bootstrap,
  monitoring, storage upload/download, and cleanup. Zero ongoing cost (pods
  terminated after job).
---

# gpu2runpod skill

Self-contained RunPod job runner with RunPod S3 Network Volume storage.

## Setup (already complete on this machine)

- Skill code: `C:\Users\apart\Projects\claude-skills\gpu2runpod\`
- Keys at `keys/`:
  - `runpod.key` — RunPod API key (plain text)
  - `runpod_storage.key` — JSON: `{endpoint, access_key, secret_key, volume_id}`
  - `huggingface.key` — optional HuggingFace token
  - `ssh/` — auto-generated ED25519 key pair on first run
- Python deps installed: `runpod`, `boto3`, `pyyaml`

## CLI surface

```
python C:\Users\apart\Projects\claude-skills\gpu2runpod\runpod_runner.py <command> [args]

Commands:
  run            Launch a new job on RunPod
  status         Show all current/recent jobs
  recover        Reconnect to a detached job
  cleanup        Force-clean a job
  cleanup-all    Clean orphaned resources

Common flags for `run`:
  --script "python3 -u train.py --epochs 3"  # full command to run
  --data train.py train.json model.pt         # files to upload
  --gpu RTX_4090 | A100 | H100               # GPU type
  --max-price 1.00                            # $/hour cap
  --cloud COMMUNITY | SECURE                  # cloud type (COMMUNITY is cheaper)
  --image runpod/pytorch                      # docker image (default: auto)
  --keep-alive                                # keep pod after job
  --max-hours 2                               # job-runtime cap
  --disk 40                                   # container disk GB
  --skip-smoke                                # bypass local syntax check
```

## Training-script output convention (MANDATORY for monitoring)

`[train]` prefix on phase lines, `step/total loss=X.XXXX` per step,
`=== DONE ===` on completion. Must `assert torch.cuda.is_available()` at top,
use `torch.utils.tensorboard.SummaryWriter(log_dir="runs")`, and
`sys.stdout.flush()` after every print. Save results to `results/`.
See `CLAUDE.md` for the full template.

## When to invoke this skill

- User asks to "run on RunPod", "offload to RunPod", "use a bigger GPU"
- A training job exceeds local GPU VRAM (RTX 2060 = 6 GB) or time budget
- Fine-tuning 70M-1B parameter models (MolMIM, MoLFormer, BART-SMILES, etc.)
- Multi-day local training that fits in 1-3 h on A100/H100

## When NOT to invoke

- Tiny experiments that fit on local GPU in <30 min
- One-off CPU diagnostics
- Anything where data sensitivity matters (storage upload step)

## Cost control

- Default `--max-price 1.00` $/hour
- `--cloud COMMUNITY` is 30-50% cheaper than SECURE
- Always pair with `--max-hours` to cap runaway costs
- Pod is terminated after job completion (no idle billing)
