# GPU2Vast: Run GPU Experiments on vast.ai

Run any Python GPU training script on rented GPUs with ephemeral Cloudflare R2 storage.
Zero ongoing cost. Fully automated provisioning, monitoring, and cleanup.

## Quick Start

```bash
python gpu_runner.py run \
  --script "python train.py --epochs 3" \
  --data train.json test.json train.py \
  --gpu RTX_4090 \
  --max-price 0.80
```

## Setup (one-time)

### 1. Install dependencies
```bash
pip install vastai boto3
```

### 2. API Keys (stored in `keys/`)
- `vastai.key`: vast.ai API key (from https://cloud.vast.ai/account/)
- `r2.key`: Cloudflare R2 credentials as JSON:
  ```json
  {
    "account_id": "your_cloudflare_account_id",
    "access_key": "R2_S3_access_key_id",
    "secret_key": "R2_S3_secret_access_key"
  }
  ```
- `huggingface.key` (optional): HuggingFace token for gated models (Llama, etc.)

### 3. SSH Setup
```bash
python setup_ssh.py
```
Generates SSH keypair, registers with vast.ai, configures `~/.ssh/config`.
After setup: `ssh -p <port> root@<host>.vast.ai`

## Commands

| Command | Description |
|---------|-------------|
| `run` | Run experiment on vast.ai |
| `run --keep-alive` | Run and keep instance alive for reuse |
| `rerun --instance-id ID` | Run new experiment on existing instance (skips boot) |
| `status` | Check all jobs |
| `recover --job-id ID` | Reconnect to detached job |
| `cleanup --job-id ID` | Force cleanup a job |
| `cleanup-all` | Clean all orphaned resources |

## CLI Options

### `run`
```
--script       Command to run on the instance
--data         Files to upload (scripts, data, configs)
--gpu          GPU type (RTX_4090, A100, etc.)
--max-price    Max $/hr (default: 0.50)
--spot         Use spot instances (50-70% cheaper, interruptible)
--image        Docker image (default: vastai/pytorch, pre-cached)
--keep-alive   Keep instance alive after job (for sequential experiments)
--max-hours    Max runtime before timeout (default: 2)
--disk         Disk GB (default: 30)
```

### `rerun` (reuse existing instance)
```
--instance-id  Instance ID from previous --keep-alive run
--script       Command to run
--data         New files to upload
```

### Multi-run workflow
```bash
# First run: boot instance, keep alive
python gpu_runner.py run --script "python train.py --lr 0.001" \
  --data train.py data.json --keep-alive

# Rerun on same instance (no boot, packages cached)
python gpu_runner.py rerun --instance-id 12345678 \
  --script "python train.py --lr 0.0001" --data train.py data.json

# Clean up when done
python gpu_runner.py cleanup-all
```

## How It Works

### Pipeline (7 stages, all printed to console)

1. **Create R2 bucket**: Ephemeral per-job bucket
2. **Upload data**: Scripts + data with parallel upload and checksum verification
3. **Search GPU**: Cost-aware scoring (price x transfer time x reliability)
4. **Launch instance**: Auto-retry up to 3 hosts if one fails (GPU/Docker errors, SSH broken)
5. **Wait for boot + SSH health check**: Detects broken hosts before running
6. **Monitor**: SSH log streaming + R2 progress + TensorBoard
7. **Download results**: Parallel download of weights, logs, TensorBoard runs

### What runs on the instance

The instance boots `vastai/pytorch` (pre-cached, ~60s boot), then:
1. pip install (torch, transformers, tensorboard, etc.; idempotent, skips pre-installed)
2. Download data from R2
3. Download HF model (e.g. `from_pretrained("distilbert-base-uncased")`)
4. Start TensorBoard on port 6006
5. Run your training script
6. Upload results + logs to R2
7. Signal done via `done.json`

### Cleanup (guaranteed)

- `finally` block always destroys instance + deletes R2 bucket
- Works on success, failure, exception, or Ctrl+C (detach mode)
- `cleanup-all` command sweeps any orphaned resources
- SSH tunnel processes cleaned via atexit + SIGTERM handler

### Resilience

- **Bad hosts**: Auto-retry up to 3 different offers on boot failure
- **SSH health check**: Verifies SSH works before starting training
- **Docker errors**: Detects "failed to create container" with 3-strike grace period
- **Instance crashes**: Liveness detection during monitoring
- **Partial uploads**: Parallel upload/download with retry on failure
- **Stale progress**: Warning at 3min, critical at 5min, checks instance alive

## Observability

### TensorBoard (real-time, in browser)

TensorBoard auto-starts on port 6006 on the instance.
Access via SSH tunnel: `ssh -p <port> root@<host> -L 6006:localhost:6006`
then open `http://localhost:6006`.

Training scripts using the observer module or PyTorch `SummaryWriter` log scalars automatically.

### SSH Log Streaming (during run)

Real-time training output via SSH tail of `/var/log/onstart.log`.
Shows: pip install progress, R2 download, model loading, training steps, loss values.

### R2 Progress (during run)

`progress.json` uploaded every 15s with: step, loss, epoch, GPU utilization, VRAM, temperature, current phase.
Checkpoint files (`.pt`, `.safetensors`) streamed to R2 during training (survives crashes).

### End of Run (downloaded locally)

- `results/`: model weights, predictions, any output files
- `results/tensorboard_runs/`: TensorBoard event files (viewable offline)
- `logs/stdout.log`: complete training stdout

### Cost + ETA Estimation

Printed before launch with per-phase breakdown:
```
ETA: ~11 min total, ~$0.0440
  upload=0m  boot=2m  setup=3m  train=5m  fetch=0m
```

### Training Script Output Convention

When Claude generates training scripts for GPU2Vast, it MUST include these
print statements so the monitoring loop can stream progress in real-time.
All prints must use `sys.stdout.flush()` after each line.

```python
import sys

# Phase markers (detected by SSH log streaming)
print("[train] Loading model from HuggingFace..."); sys.stdout.flush()
print(f"[train] Model loaded: {model_name} ({params:,} params) on {device}"); sys.stdout.flush()

print("[train] Loading data..."); sys.stdout.flush()
print(f"[train] Loaded {len(data)} samples"); sys.stdout.flush()

print("[train] Training ({total_steps} steps)..."); sys.stdout.flush()
for step in range(1, total_steps + 1):
    loss = train_step()
    # This format is parsed by progress_reporter.py
    print(f"  {step}/{total_steps} loss={loss:.4f} epoch={epoch}"); sys.stdout.flush()

print(f"[train] Eval: loss={eval_loss:.4f}, accuracy={accuracy:.4f}"); sys.stdout.flush()

print("[train] Saving results..."); sys.stdout.flush()
print(f"[train] Loss: {initial_loss:.4f} -> {final_loss:.4f}"); sys.stdout.flush()
print("[train] === DONE ==="); sys.stdout.flush()
```

Key rules:
- `[train]` prefix for phase markers
- `step/total loss=X.XXXX` format for progress (parsed by progress_reporter)
- `epoch=N` in step lines for epoch tracking
- `=== DONE ===` as completion marker
- `sys.stdout.flush()` after every print (SSH tail won't see buffered output)

### Observer Module (optional, advanced)

For automatic R2 + TensorBoard reporting without manual prints:

```python
from gpu2vast_observer import observer

observer.phase("loading_model")
model = load_model()

observer.phase("training")
for step in range(total_steps):
    loss = train_step()
    observer.step(step + 1, total_steps, loss=loss, epoch=epoch, lr=lr)

observer.done(final_loss=loss)
```

Automatically reports to R2 progress.json + TensorBoard. No-op if R2 env vars not set.

## Architecture

```
Local Machine                    vast.ai Instance
+-----------+                    +-------------------+
| gpu_runner|--[R2 upload]------>| pip install       |
|           |                    | R2 download data  |
|           |--[vast API]------->| HF model download |
|           |                    | TensorBoard :6006 |
|           |<--[SSH tail]-------| train.py          |
|           |<--[R2 progress]----|  -> progress.json  |
|           |<--[R2 checkpts]----|  -> checkpoints/   |
|           |                    | R2 upload results |
|           |<--[R2 done.json]---|  -> done.json      |
|           |                    +-------------------+
|           |--[R2 download]---->results/
|           |--[vast destroy]--->X (instance gone)
|           |--[R2 delete]------>X (bucket gone)
+-----------+
```

## Files

| File | Description |
|------|-------------|
| `gpu_runner.py` | Main CLI orchestrator (7-stage pipeline, retry, health check) |
| `vastai_manager.py` | vast.ai Python API (search, create, destroy, SSH, tunnels, health check) |
| `r2_manager.py` | Cloudflare R2 S3 client (parallel uploads/downloads, retry) |
| `setup_ssh.py` | One-command SSH key setup |
| `container/onstart.sh` | Instance entry point (install, download, train, upload) |
| `container/progress_reporter.py` | Background R2 progress + checkpoint streamer |
| `container/gpu2vast_observer.py` | Drop-in observer for training scripts (TensorBoard + R2) |
| `test_e2e_full.py` | Full E2E: PyTorch + Transformers + TensorBoard + cost estimation |
| `test_comprehensive.py` | Validation test (46+ checks across 6 phases) |

## Known Issues + Workarounds

| Issue | Workaround |
|-------|-----------|
| vast.ai host has broken GPU/Docker | Auto-retry on different host (up to 3) |
| SSH port forwarding fails on host | SSH health check detects, retries |
| `vastai/pytorch` missing torch on some hosts | Always pip install torch (no-op if present) |
| HF image (15GB) takes 5+ min to pull | Use `vastai/pytorch` + pip install instead |
| TensorBoard no direct port access | SSH tunnel fallback |
| Windows Git Bash path translation | Avoid /tmp in Python, use project dir |

## Cost

- Typical experiment: $0.02-0.15 (2-10 min on RTX 4090)
- Spot instances: 50-70% cheaper than on-demand
- R2 storage: $0.00 (free tier, deleted after use)
- Cost + ETA printed before launch
- No ongoing charges (ephemeral everything)
