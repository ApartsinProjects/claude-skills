---
name: gpu2vast
description: >
  Run any GPU-intensive PyTorch training, fine-tuning, encoding, or inference job
  on rented vast.ai GPUs (RTX 4090, A100, H100, etc.) with ephemeral Cloudflare R2
  storage. Use when local GPU is too small/slow, when a job needs more VRAM than
  available locally (e.g. RTX 2060 6 GB), when you need NeMo/BioNeMo containers,
  when training would take days locally but minutes on A100, when fine-tuning
  large pretrained models (MolMIM, ChemBERTa-2, MoLFormer-XL, BART, etc.), or
  when the user explicitly asks to "offload to vast.ai", "run on vast", "use a
  bigger GPU", or "rent a GPU". Fully automated provisioning, monitoring, R2
  upload/download, and cleanup. Zero ongoing cost (instances destroyed after job).
---

# gpu2vast skill

Self-contained vast.ai job runner with ephemeral R2 storage.

## Setup (already complete on this machine)

- Skill code: `C:\Users\apart\Projects\claude-skills\gpu2vast\`
- Keys at `keys/`: `vastai.key`, `r2.key`, `huggingface.key`, `accounts.json`, `ssh/`
- Python deps installed: `vastai`, `boto3`

## CLI surface

```
python C:\Users\apart\Projects\claude-skills\gpu2vast\gpu_runner.py <command> [args]

Commands:
  run            Launch a new job on vast.ai
  rerun          Reuse an alive instance for another job
  status         Show all current/recent jobs
  recover        Reconnect to a detached job
  cleanup        Force-clean a job
  cleanup-all    Clean orphaned resources

Common flags for `run`:
  --script "python train.py --epochs 3"   # full command to run
  --data train.py train.json model.pt     # files to upload
  --gpu RTX_4090 | A100 | H100            # GPU type
  --max-price 0.80                         # $/hour cap
  --spot                                   # use spot instances (50-70 % cheaper)
  --image vastai/pytorch                   # docker image (default)
  --keep-alive                             # keep instance for sequential reuse
  --max-hours 2                            # job-runtime cap
  --disk 30                                # disk GB
```

## Training-script output convention (MANDATORY for monitoring)

Scripts must emit `[train]` prefix lines, `step/total loss=X.XXXX` per step,
and `=== DONE ===` on completion. They must `assert torch.cuda.is_available()`
at the top, and use `torch.utils.tensorboard.SummaryWriter` for metrics. See
`CLAUDE.md` for the full template.

## When to invoke this skill

- User asks to "offload", "use vast", "run on bigger GPU", "rent a GPU"
- A training job would exceed local GPU VRAM or time budget
- A pretrained model needs NeMo / BioNeMo / Megatron container that isn't
  installed locally
- Fine-tuning a 70 M-1 B parameter model (MolMIM, MoLFormer, BART-Smiles, etc.)
- Multi-day local training that fits in 1-3 h on A100/H100

## When NOT to invoke

- Tiny experiments that fit on local GPU in <30 min — keep them local for
  iteration speed
- One-off CPU diagnostics (no GPU benefit)
- Anything where data sensitivity matters (R2 upload step puts data on
  Cloudflare for the job lifetime)

## Cost control

- Default `--max-price 0.50` $/hour
- `--spot` flag drops price 50-70 % at the cost of interruptibility
- Always pair with `--max-hours` to cap runaway costs
- Instance is destroyed after job completion (no idle billing)
