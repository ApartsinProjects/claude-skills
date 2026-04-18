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
This generates an SSH keypair, registers it with vast.ai, and configures `~/.ssh/config`.
After setup, connect to any instance with: `ssh -p <port> root@<host>.vast.ai`

## Commands

| Command | Description |
|---------|-------------|
| `run` | Run experiment on vast.ai |
| `status` | Check all jobs |
| `recover --job-id ID` | Reconnect to detached job |
| `cleanup --job-id ID` | Force cleanup a job |
| `cleanup-all` | Clean all orphaned resources |

## How It Works

### Pipeline (7 stages, all printed to console)

1. **Create R2 bucket**: Ephemeral per-job bucket for data transfer
2. **Upload data**: Training scripts + data files with checksum verification
3. **Search GPU**: Cost-aware selection (price, network, reliability, VRAM)
4. **Launch instance**: Create vast.ai instance with pre-cached `vastai/pytorch` image
5. **Wait for boot**: Poll instance status, detect docker image errors early
6. **Monitor**: Stream logs via SSH + poll R2 for training metrics
7. **Download results**: Fetch model weights, logs, predictions locally

### Cleanup (guaranteed)
- Instance is always destroyed (success, failure, or crash)
- R2 bucket + all objects deleted after download
- Ctrl+C detaches (job continues, use `recover` to reconnect)

### Observability

**Live streaming** (during run):
- SSH tail of `/var/log/onstart.log` (training stdout)
- R2 `progress.json` every 10-15s (step, loss, epoch, GPU util, phase)
- vast.ai system logs (boot, SSH, daemon)

**End of run** (downloaded locally):
- `results/`: model weights, predictions, any output files
- `logs/stdout.log`: complete training stdout
- `logs/onstart.log`: full bootstrap + training log

### Training Script Observability

Import the observer in your training script for automatic R2 progress reporting:

```python
from gpu2vast_observer import observer

observer.phase("loading_model")
model = load_model()

observer.phase("training")
for step in range(total_steps):
    loss = train_step()
    observer.step(step + 1, total_steps, loss=loss, epoch=epoch, lr=lr)

observer.phase("evaluating")
val_loss = evaluate()
observer.metric(val_loss=val_loss, val_acc=accuracy)

observer.phase("saving")
save_model()
observer.done(final_loss=loss)
```

### Cost-Aware Instance Selection

Instances are scored by total cost-effectiveness, not just price:
- Base price per hour
- Network speed (slow transfers increase total cost)
- Reliability (failures waste money)
- GPU VRAM (OOM retries waste money)

## Architecture

```
Local Machine                    vast.ai Instance
+-----------+                    +-----------------+
| gpu_runner|--[R2 upload]------>| onstart.sh      |
|           |                    |   pip install    |
|           |--[vast API]------->|   R2 download    |
|           |                    |   train.py       |
|           |<--[SSH tail]-------|   progress_reporter
|           |<--[R2 poll]--------|   R2 upload      |
|           |                    +-----------------+
|           |--[R2 download]---->results/
|           |--[vast destroy]--->X (instance gone)
|           |--[R2 delete]------>X (bucket gone)
+-----------+
```

## Files

| File | Description |
|------|-------------|
| `gpu_runner.py` | Main CLI orchestrator (7-stage pipeline) |
| `vastai_manager.py` | vast.ai Python API wrapper (search, create, destroy, SSH, logs) |
| `r2_manager.py` | Cloudflare R2 S3 client (bucket lifecycle) |
| `setup_ssh.py` | One-command SSH key setup |
| `container/onstart.sh` | Runs on instance (install, download, train, upload) |
| `container/progress_reporter.py` | Background R2 progress updater |
| `container/gpu2vast_observer.py` | Drop-in observer for training scripts |
| `container/entrypoint.sh` | Docker entrypoint (alternative to onstart) |
| `test_comprehensive.py` | Full E2E validation (6 phases, 40+ checks) |

## Cost

- Typical experiment: $0.01-0.15 (1-10 min on RTX 4090)
- R2 storage: $0.00 (free tier, deleted after use)
- No ongoing charges (ephemeral everything)
