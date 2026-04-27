---
name: gpu2runpod
description: >
  Run any GPU-intensive deep learning job on rented RunPod GPUs (RTX 4090,
  A100, H100, etc.) using RunPod S3-compatible Network Volume storage.
  Workloads include: fine-tuning, pre-training, inference/generation,
  embedding encoding, batch scoring, evaluation, model export/quantization,
  diffusion sampling, multi-modal tasks, and any other PyTorch or
  HuggingFace-based GPU job. Use when local GPU is too small/slow, when a
  job needs more VRAM than available locally (e.g. RTX 2060 6 GB), when the
  user explicitly asks to "run on RunPod", "use RunPod", "offload to RunPod",
  "use a bigger GPU", or "rent a GPU on RunPod". Fully automated
  provisioning, SSH bootstrap, monitoring, storage upload/download, and
  cleanup. Zero ongoing cost (pods terminated after job).
---

# gpu2runpod skill

Self-contained RunPod job runner with RunPod S3 Network Volume storage.
Handles any PyTorch / HuggingFace deep learning workload.

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

## Supported Workload Types

| Workload | Example script flag | Notes |
|----------|---------------------|-------|
| Fine-tuning (LoRA / QLoRA) | `python3 -u finetune.py` | peft + trl + bitsandbytes available |
| Full pre-training | `python3 -u pretrain.py` | Use A100 / H100 for memory |
| Inference / generation | `python3 -u infer.py` | Batch generation, sampling loops |
| Embedding encoding | `python3 -u encode.py` | Sentence-transformers or custom |
| Batch scoring / reranking | `python3 -u score.py` | Large-scale pairwise scoring |
| Model evaluation | `python3 -u eval.py` | Perplexity, accuracy, BLEU, etc. |
| Model export / quantization | `python3 -u export.py` | ONNX, GGUF, AWQ, GPTQ |
| Diffusion sampling | `python3 -u sample.py` | Stable Diffusion, DiT, etc. |
| Multi-modal tasks | `python3 -u multimodal.py` | CLIP, BLIP, LLaVA, etc. |
| Data processing / tokenization | `python3 -u preprocess.py` | CPU-heavy but GPU optional |
| Custom CUDA kernels | `python3 -u custom.py` | Any torch.cuda workload |

## Script output convention (MANDATORY for monitoring)

```python
import sys
import torch

assert torch.cuda.is_available(), "CUDA not available. This script requires a GPU."
device = torch.device("cuda")
print(f"[train] GPU: {torch.cuda.get_device_name(0)}"); sys.stdout.flush()

print("[train] Loading model..."); sys.stdout.flush()
print(f"[train] Model loaded: {model_name} ({params:,} params)"); sys.stdout.flush()

print("[train] Starting work..."); sys.stdout.flush()
for step in range(1, total_steps + 1):
    result = do_work()
    print(f"  {step}/{total_steps} loss={loss:.4f}"); sys.stdout.flush()

print("[train] === DONE ==="); sys.stdout.flush()
```

Rules:
- `assert torch.cuda.is_available()` at the top, before any model loading
- `[train]` prefix on phase markers (use for any workload, not just training)
- `step/total loss=X.XXXX` or `step/total metric=X.XXXX` per step
- `sys.stdout.flush()` after every print
- `=== DONE ===` as completion marker
- Save ALL outputs to `results/` (only this dir gets uploaded)
- Use `torch.utils.tensorboard.SummaryWriter(log_dir="runs")` for metrics
- Copy `runs/` into `results/tb_runs/` before exit so TensorBoard logs upload

See `CLAUDE.md` for the full template and TensorBoard snippet.

## When to invoke this skill

- User asks to "run on RunPod", "offload to RunPod", "use a bigger GPU"
- Job exceeds local GPU VRAM (RTX 2060 = 6 GB) or local time budget
- Any PyTorch / HuggingFace workload: fine-tuning, inference, encoding, scoring, eval, export, diffusion, multi-modal
- Multi-hour or multi-day work that fits in 1-4 h on A100/H100
- Batch jobs that benefit from fast GPU memory bandwidth (large model inference)

## When NOT to invoke

- Tiny experiments that fit on local GPU in under 30 min
- CPU-only diagnostics or pure data analysis
- Jobs with data sensitivity concerns (files are uploaded to RunPod storage)

## Cost control

- Default `--max-price 1.00` $/hour
- `--cloud COMMUNITY` is 30-50% cheaper than SECURE
- Always pair with `--max-hours` to cap runaway costs
- Pod is terminated after job completion (no idle billing)

## GPU recommendations by workload

| Use case | Recommended GPU | Reason |
|----------|-----------------|--------|
| LoRA / QLoRA fine-tune (7B) | RTX_4090 | 24 GB, cheap, fast |
| LoRA fine-tune (13B+) | A100 or L40S | 40-80 GB |
| Full pre-training | H100 or A100_SXM | HBM bandwidth |
| Inference (70B+ int4) | A100_PCIE 80GB | Fits in single GPU |
| Diffusion (image/video) | RTX_4090 or L40S | VRAM + speed balance |
| Encoding large corpus | RTX_4090 | High throughput, cheap |
| Model export / quant | RTX_4090 | VRAM depends on model size |
