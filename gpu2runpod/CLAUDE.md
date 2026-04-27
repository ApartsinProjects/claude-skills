# GPU2RunPod Skill Instructions

This skill runs any GPU training job (fine-tuning, embeddings, inference) on rented RunPod GPUs.
Framework: PyTorch + Transformers + HuggingFace ecosystem + TensorBoard.
Skill location: `C:\Users\apart\Projects\claude-skills\gpu2runpod\`

## Training Script Output Convention

Training scripts MUST follow this format for real-time monitoring via SSH streaming.

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

print(f"[train] Training ({total_steps} steps)..."); sys.stdout.flush()
for step in range(1, total_steps + 1):
    loss = train_step()
    print(f"  {step}/{total_steps} loss={loss:.4f} epoch={epoch}"); sys.stdout.flush()

print(f"[train] Eval: loss={eval_loss:.4f}, accuracy={accuracy:.4f}"); sys.stdout.flush()
print(f"[train] Loss: {initial_loss:.4f} -> {final_loss:.4f}"); sys.stdout.flush()
print("[train] === DONE ==="); sys.stdout.flush()
```

Rules:
- **MANDATORY**: `assert torch.cuda.is_available()` at the top of every script, before any model loading.
- `[train]` prefix on phase markers
- `step/total loss=X.XXXX` format for training progress
- `epoch=N` in step lines for epoch tracking
- `sys.stdout.flush()` after EVERY print (SSH log streaming needs unbuffered output)
- `=== DONE ===` as completion marker
- Save all results to `results/` directory
- **MANDATORY**: Use `torch.utils.tensorboard.SummaryWriter(log_dir="runs")` for logging

TensorBoard template (same as gpu2vast):
```python
from torch.utils.tensorboard import SummaryWriter
writer = SummaryWriter(log_dir="runs")
writer.add_text("phase", "model_download: loading model", 0); writer.flush()
# ... per step: writer.add_scalar("train/loss", loss, step)
# ... at eval: writer.add_scalar("eval/loss", eval_loss, epochs)
writer.close()
# Copy to results: shutil.copytree("runs", "results/tb_runs", dirs_exist_ok=True)
```

## Observability Packages

The onstart.sh installs these packages on the pod:
`boto3 transformers accelerate peft trl bitsandbytes sentence-transformers datasets
 requests tensorboard sentencepiece protobuf pynvml psutil`

- `pynvml` (nvidia-ml-py3): GPU utilization, memory, temperature, power draw
- `psutil`: CPU/RAM monitoring
- `tensorboard`: training metrics
- `torch.profiler`: built-in CUDA kernel profiling (heavyweight, use manually)

Note: `torch` is skipped if already present in the base image.

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
- `--skip-smoke`: bypass local import check (not recommended)

File rename syntax for `--data`: use `local_path:remote_name` to upload a local file
under a different name on the pod. Example:
```bash
--data my_experiment.py:train.py dataset_v2.json:data.json
```

## Pipeline (step by step)

| Step | What | Time | Visible in chat |
|------|------|------|-----------------|
| 0 | Local smoke test (syntax + imports) | 2s | import X: OK |
| 1 | Create R2 bucket | 1s | [r2] Bucket created |
| 2 | Upload data + scripts to R2 | 1-5s | Uploaded: file.py (1,234 bytes) |
| 3 | Find GPU type + pricing | 2s | GPU: RTX 4090 @ $0.74/hr |
| 4 | Create pod + wait for boot | 60-120s | Status: RUNNING |
| 4 | SSH health check | 5s | SSH health check: OK |
| 5 | Bootstrap (pip install + R2 download) | 2-5 min | [GPU2RunPod] Installing packages... |
| 5 | HF model download (on pod) | 5-30s | [train] Loading model... |
| 5 | TensorBoard starts (background) | auto | TensorBoard: http://localhost:6006 |
| 5 | Training runs | varies | [app] 5/20 loss=0.3456 |
| 5 | Results upload to R2 (on pod) | 5-30s | [app] Uploaded: model.safetensors |
| 6 | Download results locally | 5-30s | [r2] Downloaded: model.safetensors |
| 6 | Terminate pod + delete R2 bucket | 2s | Cleanup complete |

## Pod Lifecycle and Cleanup

- R2 bucket: created per job, deleted after results downloaded (with --auto-destroy)
- Pod: terminated in `finally` block (success, failure, exception, Ctrl+C)
- SSH tunnels: cleaned via atexit + SIGTERM
- Ctrl+C: detaches (pod keeps running, use `recover` to reconnect)
- `cleanup-all`: sweeps orphaned pods + R2 buckets

## SSH and TensorBoard

- SSH keys auto-generated on first run (`setup_ssh.py`) and injected via PUBLIC_KEY env var
- SSH health check runs after pod is RUNNING (catches broken hosts in 5s)
- TensorBoard: auto-starts on pod port 6006, SSH tunnel opened automatically
- If tunnel fails, prints manual command: `ssh -p <port> root@<host> -L 6006:localhost:6006`

## What NOT to Do

- Do NOT use Unicode/emoji in print statements (crashes Windows cp1252 console)
- Do NOT use Python 3.14's default `text=True` without `encoding="utf-8", errors="replace"`
- Do NOT forget `sys.stdout.flush()` (SSH log streaming won't show buffered output)
- Do NOT save results outside `results/` directory (won't be uploaded to R2)
- Do NOT use TensorFlow (this skill is PyTorch + HuggingFace only)

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| "No module named X" | Missing package | Add import to script (smoke test catches it). |
| Boot timeout | Slow image pull | Pod status polling waits. No action needed. |
| SSH health check failed | Broken pod | Terminate and retry. |
| Model weights missing | Saved outside results/ | Save to `results/model/`. |
| TensorBoard not opening | Unicode crash in URL | Fixed (ASCII-only). Check logs. |
| Training output not streaming | Missing flush | Add `sys.stdout.flush()` after every print. |
| PUBLIC_KEY not injected | Wrong image | Use runpod/pytorch or any RunPod-compatible image. |
