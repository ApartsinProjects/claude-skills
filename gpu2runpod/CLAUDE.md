# GPU2RunPod Skill Instructions

This skill runs any GPU-intensive deep learning job on rented RunPod GPUs.
Supported workloads: fine-tuning, pre-training, inference/generation,
embedding encoding, batch scoring, evaluation, model export/quantization,
diffusion sampling, multi-modal tasks, and any other PyTorch / HuggingFace
GPU job.
Skill location: `C:\Users\apart\Projects\claude-skills\gpu2runpod\`

## Script Output Convention

Scripts MUST follow this format for real-time monitoring via SSH streaming.
The `[train]` prefix is conventional for all workloads (not just training).

```python
import sys
import torch

# MANDATORY: GPU check at the very top, before any model loading
assert torch.cuda.is_available(), "CUDA not available. This script requires a GPU."
device = torch.device("cuda")
print(f"[train] GPU: {torch.cuda.get_device_name(0)}"); sys.stdout.flush()

print("[train] Loading model from HuggingFace..."); sys.stdout.flush()
print(f"[train] Model loaded: {model_name} ({params:,} params) on {device}"); sys.stdout.flush()

print("[train] Loading data..."); sys.stdout.flush()
print(f"[train] Loaded {len(data)} samples"); sys.stdout.flush()

print(f"[train] Starting ({total_steps} steps)..."); sys.stdout.flush()
for step in range(1, total_steps + 1):
    result = do_work()
    print(f"  {step}/{total_steps} loss={loss:.4f} epoch={epoch}"); sys.stdout.flush()

print(f"[train] Eval: loss={eval_loss:.4f}, accuracy={accuracy:.4f}"); sys.stdout.flush()
print(f"[train] Loss: {initial_loss:.4f} -> {final_loss:.4f}"); sys.stdout.flush()
print("[train] === DONE ==="); sys.stdout.flush()
```

Rules:
- **MANDATORY**: `assert torch.cuda.is_available()` at the top, before any model loading
- `[train]` prefix on phase markers (works for any workload type)
- `step/total loss=X.XXXX` or `step/total metric=X.XXXX` format per step
- `sys.stdout.flush()` after EVERY print (SSH log streaming needs unbuffered output)
- `=== DONE ===` as completion marker
- Save ALL outputs to `results/` directory (only this dir gets uploaded)
- **MANDATORY**: Use `torch.utils.tensorboard.SummaryWriter(log_dir="runs")` for logging

TensorBoard template (works for any workload):
```python
from torch.utils.tensorboard import SummaryWriter
import shutil, os
writer = SummaryWriter(log_dir="runs")
writer.add_text("phase", "model_download: loading model", 0); writer.flush()
# per step (loss, accuracy, score, throughput, etc.):
writer.add_scalar("train/loss", loss, step)
writer.add_scalar("eval/score", score, step)
# at end:
writer.close()
# Copy runs/ into results/ so it gets uploaded:
os.makedirs("results", exist_ok=True)
shutil.copytree("runs", "results/tb_runs", dirs_exist_ok=True)
```

## Workload-Specific Patterns

### Fine-tuning (LoRA / QLoRA)
```python
from peft import get_peft_model, LoraConfig
from trl import SFTTrainer
# peft + trl + bitsandbytes are pre-installed by onstart.sh
# If peft conflicts with base torch, use requirements.txt
```

### Inference / Generation
```python
# Batch inference: loop over dataset, collect outputs to results/outputs.jsonl
# Progress: print step/total after each batch
import json, pathlib
out = pathlib.Path("results/outputs.jsonl")
out.parent.mkdir(exist_ok=True)
with out.open("w") as f:
    for step, batch in enumerate(loader, 1):
        outputs = model.generate(**batch)
        for item in outputs:
            f.write(json.dumps(item) + "\n")
        print(f"  {step}/{total_steps} generated={step * batch_size}"); sys.stdout.flush()
```

### Embedding Encoding
```python
# Encode large corpus, save as numpy or safetensors
import numpy as np
embeddings = []
for step, batch in enumerate(loader, 1):
    emb = model.encode(batch)
    embeddings.append(emb)
    print(f"  {step}/{total_steps} encoded={step * batch_size}"); sys.stdout.flush()
np.save("results/embeddings.npy", np.vstack(embeddings))
```

### Model Export / Quantization
```python
# ONNX export
import torch.onnx
torch.onnx.export(model, dummy_input, "results/model.onnx", ...)
print("[train] Exported ONNX"); sys.stdout.flush()

# GPTQ / AWQ: use the relevant library; save to results/quantized_model/
# bitsandbytes is pre-installed; AWQ/GPTQ may need requirements.txt
```

### Diffusion Sampling
```python
from diffusers import StableDiffusionPipeline
pipe = StableDiffusionPipeline.from_pretrained(...)
pipe = pipe.to("cuda")
for step, prompt in enumerate(prompts, 1):
    image = pipe(prompt).images[0]
    image.save(f"results/sample_{step:04d}.png")
    print(f"  {step}/{len(prompts)} sampled"); sys.stdout.flush()
```

### Batch Scoring / Reranking
```python
# Score pairs (query, candidate) with cross-encoder or custom model
import json
scores = []
for step, (q, c) in enumerate(pairs, 1):
    score = model(q, c)
    scores.append({"query": q, "candidate": c, "score": float(score)})
    print(f"  {step}/{total_steps} scored"); sys.stdout.flush()
json.dump(scores, open("results/scores.json", "w"))
```

## Observability Packages

The `onstart.sh` on the pod installs:
```
boto3 transformers accelerate peft trl bitsandbytes sentence-transformers
datasets requests tensorboard sentencepiece protobuf pynvml psutil
```

Note: if `peft` has dependency conflicts with the base image's torch version,
the install retries automatically with core packages only (boto3, transformers,
accelerate, datasets, requests, tensorboard, pynvml, psutil). Scripts that
need peft/trl should include a `requirements.txt` in `--data` for reliable
installation.

`torch` is skipped if already present in the base image (RunPod pytorch images
include it).

## Running a Job

```bash
cd C:\Users\apart\Projects\claude-skills\gpu2runpod

python runpod_runner.py run \
  --script "python3 -u train.py" \
  --data train.py data.json \
  --gpu RTX_4090 \
  --max-price 1.00
```

GPU name aliases (use any of these with `--gpu`):
- `H100`, `H100_SXM` -> NVIDIA H100 80GB HBM3
- `A100`, `A100_PCIE` -> NVIDIA A100 80GB PCIe
- `A100_SXM` -> NVIDIA A100 SXM4 80GB
- `RTX_4090` -> NVIDIA GeForce RTX 4090
- `RTX_3090` -> NVIDIA GeForce RTX 3090
- `L40S` -> NVIDIA L40S
- `L40` -> NVIDIA L40

Key flags:
- Always use `python3 -u` (unbuffered output)
- `--keep-alive`: keep pod after job (for sequential experiments)
- `--cloud COMMUNITY`: cheapest tier (default)
- `--cloud SECURE`: dedicated hardware (more reliable, pricier)
- `--skip-smoke`: bypass local syntax check (not recommended)
- `--disk 40`: container disk in GB (increase for large models/datasets)
- `--max-hours 4`: hard runtime cap to prevent runaway billing

File rename syntax for `--data`: use `local_path:remote_name` to upload a
local file under a different name on the pod. Example:
```bash
--data my_experiment.py:train.py dataset_v2.json:data.json
```

## Pipeline (step by step)

| Step | What | Time | Visible in chat |
|------|------|------|-----------------|
| 0 | Local smoke test (syntax + imports) | 2s | import X: OK |
| 1 | Create storage prefix (RunPod Network Volume) | 1s | Volume accessible |
| 2 | Upload data + scripts to storage | 1-5s | Uploaded: file.py (1,234 bytes) |
| 3 | Find GPU type + pricing | 2s | GPU: RTX 4090 @ $0.74/hr |
| 4 | Create pod + wait for boot | 20-120s | Pod reached RUNNING state in Xs |
| 4 | SSH health check | 5s | SSH health check: OK |
| 5 | Bootstrap: source env, pip install, download data | 30-120s | Installing packages... |
| 5 | TensorBoard starts (background, port 6006) | auto | TensorBoard running on pod:6006 |
| 5 | Job runs (EXPERIMENT_CMD) | varies | [train] 5/20 loss=0.3456 |
| 5 | Results upload to storage (from results/) | 2-30s | Uploaded N files |
| 6 | Download results locally | 2-30s | Downloaded: model.safetensors |
| 6 | Terminate pod + cleanup storage | 2s | Cleanup complete |

## Storage Architecture

RunPod S3 Network Volume is used for all data transfer. Each job gets an
isolated prefix: `{volume_id}/{job_id}/data/` (input files),
`{volume_id}/{job_id}/results/` (outputs).

**Important RunPod S3 limitation**: `list_objects_v2` always returns empty
(broken API). The code works around this by:
- Using `manifest.json` (written by upload_files) to track uploaded keys
- Using `done.json["files"]` (written by pod on completion) for result keys
- Using `head_object` for existence checks instead of listing
- `delete_job` rebuilds key list from manifest + done.json + known sentinel keys

## Pod Lifecycle and Cleanup

- Storage: job prefix created per run, deleted after results downloaded
- Pod: terminated in `finally` block (success, failure, exception, Ctrl+C)
- SSH tunnels: cleaned via atexit + SIGTERM
- Ctrl+C: detaches (pod keeps running, use `recover` to reconnect)
- `cleanup-all`: sweeps orphaned pods + storage prefixes

## SSH and TensorBoard

- SSH keys auto-generated on first run (ED25519, stored in `keys/ssh/`)
- PUBLIC_KEY injected as Docker env var, sourced by bootstrap from `/proc/1/environ`
- SSH health check runs after pod is RUNNING (catches broken hosts in ~5s)
- TensorBoard: auto-starts on pod port 6006; SSH tunnel opened automatically
- If tunnel fails, prints manual command: `ssh -p <port> root@<host> -L 6006:localhost:6006`
- Live pod log streamed via `tail -f /tmp/job.log` over SSH in background thread

## Bootstrap Env Var Sourcing

Docker container env vars are NOT inherited by SSH sessions. The bootstrap
and `onstart.sh` source them from `/proc/1/environ` using `printf '%q'` to
correctly quote values with spaces (e.g. `EXPERIMENT_CMD=python3 -u train.py`).
If this sourcing fails silently, check `/proc/1/environ` on the pod.

## What NOT to Do

- Do NOT use Unicode/emoji in print statements (crashes Windows cp1252 console)
- Do NOT use Python 3.14's default `text=True` without `encoding="utf-8", errors="replace"`
- Do NOT forget `sys.stdout.flush()` (SSH log streaming won't show buffered output)
- Do NOT save results outside `results/` directory (won't be uploaded to storage)
- Do NOT use TensorFlow (this skill is PyTorch + HuggingFace only)
- Do NOT assume `list_objects_v2` works on RunPod S3 (always returns empty)

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| "No module named X" | Missing package | Add to `requirements.txt` in `--data`. |
| Boot timeout (120s stall) | RunPod Community Cloud delay | Re-run; transient availability issue. |
| SSH health check failed | Broken pod allocation | Terminate pod and retry. |
| Model weights missing | Saved outside `results/` | Save to `results/model/`. |
| TensorBoard not opening | Tunnel failed | Use manual SSH tunnel command. |
| Training output not streaming | Missing flush | Add `sys.stdout.flush()` after every print. |
| EXPERIMENT_CMD truncated | Spaces in env var value | Fixed: bootstrap uses `printf '%q'` quoting. |
| "0 files downloaded" | RunPod S3 listing broken | Fixed: manifest.json used for all file lookups. |
| peft/bitsandbytes conflict | torch version mismatch | Automatic fallback to core packages; use requirements.txt for peft. |
| Done.json not written | Script exited non-zero + set -e | Fixed: `set +e` wraps eval so done.json always written. |
| Large outputs (models) slow | Multi-GB upload over S3 | Use `--keep-alive` + manual download via SSH scp if needed. |
| Out of disk space on pod | Container disk too small | Add `--disk 80` (or higher) to run command. |
