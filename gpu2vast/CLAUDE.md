# GPU2Vast Skill Instructions

When the user asks to run a GPU training job on vast.ai, follow these instructions exactly.

## Before Writing Training Scripts

Training scripts MUST follow this output convention for real-time monitoring:

```python
import sys

print("[train] Loading model from HuggingFace..."); sys.stdout.flush()
print(f"[train] Model loaded: {model_name} ({params:,} params) on {device}"); sys.stdout.flush()
print("[train] Loading data..."); sys.stdout.flush()
print(f"[train] Loaded {len(data)} samples"); sys.stdout.flush()
print("[train] Training ({total_steps} steps)..."); sys.stdout.flush()

for step in range(1, total_steps + 1):
    loss = train_step()
    print(f"  {step}/{total_steps} loss={loss:.4f} epoch={epoch}"); sys.stdout.flush()

print(f"[train] Eval: loss={eval_loss:.4f}, accuracy={accuracy:.4f}"); sys.stdout.flush()
print(f"[train] Loss: {initial_loss:.4f} -> {final_loss:.4f}"); sys.stdout.flush()
print("[train] === DONE ==="); sys.stdout.flush()
```

Rules:
- `[train]` prefix on phase markers
- `step/total loss=X.XXXX` format (parsed by progress_reporter)
- `sys.stdout.flush()` after EVERY print (SSH streaming needs unbuffered output)
- `=== DONE ===` as completion marker
- Save results to `results/` directory (uploaded to R2 automatically)
- Save model weights to `results/model/` or `results/model_weights/`
- Use `torch.utils.tensorboard.SummaryWriter(log_dir="runs")` for TensorBoard

## Before Running on vast.ai

1. **Smoke test runs automatically** (step 0/7): checks syntax + imports locally. If it fails, fix before retrying.
2. **Never use `--skip-smoke`** unless debugging the smoke test itself.
3. **Include ALL dependencies** in the training script's imports so the smoke test catches missing packages.
4. **Use `distilbert-base-uncased`** for test runs (proven to work, fast download). Switch to your target model for real runs.

## Running the Job

```bash
python gpu_runner.py run \
  --script "python3 -u train.py" \
  --data train.py data.json \
  --gpu RTX_4090 \
  --max-price 0.50
```

- Always use `python3 -u` (unbuffered output for SSH streaming)
- Image defaults to `vastai/pytorch` (pre-cached, boots in 60s). Never change this unless you have a specific reason.
- Use `--keep-alive` when running multiple experiments sequentially (saves 5-8 min boot + install per subsequent run)
- Use `--spot` for non-critical experiments (50-70% cheaper)

## What to Expect

- **Boot**: 60-90s (vastai/pytorch pre-cached). Activity-based timeout, no hard limit.
- **SSH health check**: Runs automatically after boot. Bad hosts auto-retry (up to 3).
- **pip install**: 2-5 min first time (torch already installed, installs transformers + deps). Instant on `--keep-alive` reruns.
- **TensorBoard**: Opens in browser automatically via SSH tunnel (background, non-blocking).
- **Training output**: Streams via SSH every 5s in chat. All `[train]` lines visible.
- **Results**: Downloaded to `--local-results` directory. Model weights, logs, TensorBoard runs.
- **Cleanup**: Instance destroyed + R2 bucket deleted automatically (even on failure).

## Important: What NOT to Do

- Do NOT use `huggingface/transformers-pytorch-gpu` image (15GB, 5+ min pull, causes timeouts)
- Do NOT use Unicode characters in print statements (crashes Windows cp1252 console)
- Do NOT use double quotes inside `python3 -c "..."` embedded in bash (use single quotes or write separate .py files)
- Do NOT join bash commands with `&&` when backgrounding processes (`& &&` is invalid bash)
- Do NOT use `--no-cache-dir` with pip (forces re-downloading everything)
- Do NOT forget `sys.stdout.flush()` after prints (SSH tail won't see buffered output)

## Sequential Experiments (--keep-alive)

```bash
# First run: boot + install (slow)
python gpu_runner.py run --script "python3 -u train.py --lr 0.001" \
  --data train.py data.json --keep-alive

# Subsequent runs: reuse instance (fast, packages cached)
python gpu_runner.py rerun --instance-id 12345678 \
  --script "python3 -u train.py --lr 0.0001" --data train.py data.json

# Clean up when done
python gpu_runner.py cleanup-all
```

## Troubleshooting

- **"No module named X"**: Add X to the training script imports so smoke test catches it. Also add to onstart.sh pip install list.
- **Boot timeout**: Instance is still making progress (apt-get, layer pull). Wait. Activity-based timeout handles this.
- **SSH health check failed**: Host is broken. Auto-retries on next offer.
- **Model weights not downloaded**: Check that training script saves to `results/` (not a different directory). Upload uses `results/**/*` recursive glob.
- **TensorBoard not opening**: Check for Unicode crash in logs. Use ASCII-only output.
