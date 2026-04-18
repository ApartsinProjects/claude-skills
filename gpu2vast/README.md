# GPU2Vast: Run GPU Experiments on vast.ai

Run any Python GPU training script on rented GPUs with ephemeral Cloudflare R2 storage.
Zero ongoing cost. Fully automated provisioning, monitoring, and cleanup.

## Quick Start

```bash
gpu2vast run \
  --script "python train.py --epochs 3" \
  --data train.json test.json train.py \
  --gpu A100 \
  --max-price 0.80
```

## Setup (one-time)

### 1. Install vast.ai CLI
```bash
pip install vastai
```

### 2. API Keys (stored in ~/.claude/skills/gpu2vast/keys/)
- `vastai.key` - vast.ai API key (from https://cloud.vast.ai/account/)
- `r2.key` - Cloudflare R2 credentials as JSON:
  ```json
  {
    "account_id": "your_cloudflare_account_id",
    "access_key": "R2_S3_access_key_id",
    "secret_key": "R2_S3_secret_access_key"
  }
  ```
  Create R2 API token at: Cloudflare Dashboard → R2 → Manage R2 API Tokens → Create API Token

### 3. Docker Hub (for custom images)
```bash
docker login
```

### 4. HuggingFace (for gated models like Llama)
```bash
pip install huggingface_hub
huggingface-cli login
```

## Commands

| Command | Description |
|---------|-------------|
| `gpu2vast run` | Run experiment on vast.ai |
| `gpu2vast status` | Check running jobs |
| `gpu2vast recover JOB_ID` | Reconnect to detached job |
| `gpu2vast cleanup JOB_ID` | Kill instance + delete R2 bucket |
| `gpu2vast cleanup-all` | Clean all orphaned resources |
| `gpu2vast list-buckets` | Show R2 buckets |
| `gpu2vast setup` | Configure credentials |

## How It Works

1. Creates ephemeral R2 bucket, uploads your data + scripts
2. Finds cheapest matching GPU on vast.ai
3. Launches Docker container with PyTorch + your data
4. Monitors progress via R2 (container writes progress.json every 30s)
5. Downloads results when done
6. Destroys instance + deletes R2 bucket

## Cost

- Typical experiment: $0.05-0.15 (5-10 min on A100)
- R2 storage: $0.00 (free tier, deleted after use)
- No ongoing charges
