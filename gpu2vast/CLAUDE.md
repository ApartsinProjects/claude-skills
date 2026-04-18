# GPU2Vast Skill Instructions

This skill runs any GPU training job (fine-tuning, embeddings, inference) on rented vast.ai GPUs.
Framework: PyTorch + Transformers + HuggingFace ecosystem + TensorBoard.
Skill location: `C:\Users\apart\Projects\claude-skills\gpu2vast\`

## Training Script Output Convention

Training scripts MUST follow this format for real-time monitoring via SSH streaming.
The progress_reporter parses these patterns from stdout.

```python
import sys

print("[train] Loading model from HuggingFace..."); sys.stdout.flush()
print(f"[train] Model loaded: {model_name} ({params:,} params) on {device}"); sys.stdout.flush()

print("[train] Loading data..."); sys.stdout.flush()
print(f"[train] Loaded {len(data)} samples"); sys.stdout.flush()

print(f"[train] Training ({total_steps} steps)..."); sys.stdout.flush()
for step in range(1, total_steps + 1):
    loss = train_step()
    # This exact format is parsed by progress_reporter.py
    print(f"  {step}/{total_steps} loss={loss:.4f} epoch={epoch}"); sys.stdout.flush()

print(f"[train] Eval: loss={eval_loss:.4f}, accuracy={accuracy:.4f}"); sys.stdout.flush()
print(f"[train] Loss: {initial_loss:.4f} -> {final_loss:.4f}"); sys.stdout.flush()
print("[train] === DONE ==="); sys.stdout.flush()
```

Rules:
- `[train]` prefix on phase markers (model loading, data loading, training, eval, saving)
- `step/total loss=X.XXXX` format for training progress
- `epoch=N` in step lines for epoch tracking
- `sys.stdout.flush()` after EVERY print (SSH tail needs unbuffered output)
- `=== DONE ===` as completion marker
- Save all results to `results/` directory (subdirs OK: `results/model/`, `results/logs/`)
- **MANDATORY**: Use `torch.utils.tensorboard.SummaryWriter(log_dir="runs")` for logging all metrics
- **MANDATORY**: Log at minimum: `train/loss` per step, `eval/accuracy` at end, `eval/loss` at end
- **MANDATORY**: Use `writer.add_text("phase", ...)` to log each phase transition (see template below)
- **MANDATORY**: Call `writer.flush()` after the first `add_text` call so TensorBoard has data immediately on open
- Copy TensorBoard runs to results: `shutil.copytree("runs", "results/tb_runs", dirs_exist_ok=True)`

TensorBoard logging template (include in every training script):
```python
from torch.utils.tensorboard import SummaryWriter
writer = SummaryWriter(log_dir="runs")

# Phase markers via add_text (tag="phase", use global_step for ordering)
# Create the writer BEFORE any work, log phases as they happen:
writer.add_text("phase", "model_download: loading distilbert-base-uncased", 0)
writer.flush()  # flush early so TensorBoard shows data on first open
# ... load model ...
writer.add_text("phase", f"model_loaded: distilbert-base-uncased on {device}", 0)

writer.add_text("phase", "data_loading: tokenizing training texts", 0)
# ... load/tokenize data ...
writer.add_text("phase", f"data_loaded: {len(dataset)} samples tokenized", 0)

writer.add_text("phase", f"training_start: {total_steps} steps, {epochs} epochs, lr={lr}", 0)
writer.flush()

# Per-epoch markers:
for epoch in range(1, epochs + 1):
    writer.add_text("phase", f"epoch_start: epoch {epoch}/{epochs}", epoch)
    # Training loop:
    writer.add_scalar("train/loss", loss, step)
    writer.add_scalar("train/lr", lr, step)
    writer.add_text("phase", f"epoch_end: epoch {epoch}, avg_loss={avg_loss:.4f}", epoch)

writer.add_text("phase", f"training_complete: {elapsed:.1f}s", epochs)

# Evaluation:
writer.add_text("phase", "eval_start: computing metrics", epochs)
writer.add_scalar("eval/loss", eval_loss, epochs)
writer.add_scalar("eval/accuracy", accuracy, epochs)
writer.add_text("phase", f"eval_complete: loss={eval_loss:.4f}, acc={accuracy:.4f}", epochs)

# Saving:
writer.add_text("phase", "saving_results: model + summary to results/", epochs)
# ... save ...
writer.add_text("phase", f"done: saved, {elapsed:.1f}s total, perplexity={ppl:.2f}", epochs)
writer.close()
```

Required `add_text("phase", ...)` entries (minimum set for every training script):
- `model_download` / `model_loaded`
- `data_loading` / `data_loaded`
- `training_start`
- `epoch_start` / `epoch_end` (per epoch)
- `training_complete`
- `eval_start` / `eval_complete`
- `saving_results` / `done`

## Dependencies

The onstart.sh installs these packages on the instance:
`boto3 transformers accelerate peft trl bitsandbytes sentence-transformers datasets requests tensorboard sentencepiece protobuf`
Note: `torch` is skipped if already present in the base image (vastai/pytorch has it pre-installed).

If your script needs additional packages, add a `requirements.txt` to `--data` files.
The smoke test (step 0) checks imports locally before launching.

## Running a Job

```bash
cd C:\Users\apart\Projects\claude-skills\gpu2vast

python gpu_runner.py run \
  --script "python3 -u train.py" \
  --data train.py data.json \
  --gpu RTX_4090 \
  --max-price 0.50
```

Key flags:
- Always use `python3 -u` (unbuffered output)
- `--keep-alive`: keep instance after job (for sequential experiments)
- `--spot`: use interruptible instances (50-70% cheaper)
- `--skip-smoke`: bypass local import check (not recommended)
- `--image auto`: always resolves to `vastai/pytorch` (pre-cached, fastest boot)

File rename syntax for `--data`: use `local_path:remote_name` to upload a local file
under a different name on the instance. Example:
```bash
--data my_experiment.py:train.py dataset_v2.json:data.json
```
This uploads `my_experiment.py` as `train.py` and `dataset_v2.json` as `data.json`.

## Pipeline (what happens step by step)

| Step | What | Time | Visible in chat |
|------|------|------|-----------------|
| 0 | Local smoke test (syntax + imports) | 2s | import X: OK |
| 1 | Create R2 bucket | 1s | [r2] Bucket created |
| 2 | Upload data + scripts to R2 | 1-5s | Uploaded: file.py (1,234 bytes) |
| 3 | Search GPU + cost/ETA estimate | 2s | ETA: ~11 min, ~$0.04 |
| 4 | Launch instance (retry up to 3 hosts) | 1s | Instance created: 12345678 |
| 5 | Boot + SSH health check | 60-90s | Status: loading [...] / SSH health check: OK |
| 6 | pip install (on instance) | 2-5 min | [app] [GPU2Vast] Installing packages... |
| 6 | R2 data download (on instance) | 1-5s | [app] Downloaded: data.json |
| 6 | HF model download (on instance) | 5-30s | [app] [train] Loading model... |
| 6 | TensorBoard starts (background) | auto | TensorBoard: http://localhost:6006 |
| 6 | Training runs | varies | [app] 5/20 loss=0.3456 |
| 6 | Results upload to R2 (on instance) | 5-30s | [app] Uploaded: model.safetensors |
| 7 | Download results locally | 5-30s | [r2] Downloaded: model.safetensors |
| 7 | Destroy instance + delete R2 bucket | 2s | Cleanup complete |

## Instance Lifecycle and Cleanup

- R2 bucket: created per job, deleted after results downloaded (even on failure)
- Instance: destroyed in `finally` block (success, failure, exception, Ctrl+C)
- SSH tunnels: cleaned via atexit + SIGTERM signal handlers
- Ctrl+C: detaches (instance keeps running, use `recover` to reconnect)
- `cleanup-all`: sweeps any orphaned instances + R2 buckets

## SSH and TensorBoard

- SSH keys auto-generated on first run (`setup_ssh.py`) and registered with vast.ai
- SSH health check runs immediately when instance reports "running" (catches broken hosts in 5s)
- TensorBoard: auto-starts on port 6006 on instance
- SSH tunnel opened automatically in background thread (non-blocking)
- Browser opens automatically when TensorBoard responds
- If tunnel fails, prints manual command: `ssh -p <port> root@<host> -L 6006:localhost:6006`

## Boot and Timeout Behavior

- Uses **activity-based timeout** (not hard wall-clock)
- Keeps waiting as long as status_msg is changing (image pulling, apt-get, etc.)
- Only gives up after 120s of NO activity
- SSH health check runs immediately on boot (before onstart script)
- If SSH fails, destroys instance and retries on next offer (up to 3 attempts)

## Sequential Experiments (--keep-alive)

For multiple experiments on the same setup (saves 5-8 min boot + install):

```bash
# First run: boot + install (slow, ~8 min setup)
python gpu_runner.py run --script "python3 -u train.py --lr 0.001" \
  --data train.py data.json --keep-alive

# Subsequent runs: reuse instance (fast, ~10s setup)
python gpu_runner.py rerun --instance-id 12345678 \
  --script "python3 -u train.py --lr 0.0001" --data train.py data.json

# When done with all experiments
python gpu_runner.py cleanup-all
```

## What NOT to Do

- Do NOT use `huggingface/transformers-pytorch-gpu` image (15GB, 5+ min pull, causes timeouts)
- Do NOT use Unicode/emoji in print statements (crashes Windows cp1252 console)
- Do NOT use Python 3.14's default `text=True` in subprocess without `encoding="utf-8", errors="replace"` (SSH output contains non-ASCII that crashes cp1252)
- Do NOT use double quotes inside `python3 -c "..."` embedded in bash
- Do NOT join bash commands with `&&` when backgrounding processes (`& &&` is invalid)
- Do NOT use `--no-cache-dir` with pip (forces re-downloading 2GB+ of packages)
- Do NOT forget `sys.stdout.flush()` (SSH tail won't see buffered output)
- Do NOT save results outside `results/` directory (won't be uploaded to R2)
- Do NOT use TensorFlow (this skill is PyTorch + HuggingFace only)

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| "No module named X" | Missing package | Add import to script (smoke test catches it). Add to onstart.sh pip list. |
| Boot timeout | Slow image build | Activity timeout waits automatically. No action needed. |
| SSH health check failed | Broken host | Auto-retries on next offer (up to 3). |
| Model weights missing | Saved outside results/ or glob didn't recurse | Save to `results/model/`. Upload uses `results/**/*`. |
| TensorBoard not opening | Unicode crash in URL box | Fixed (ASCII-only). Check logs for errors. |
| pip install slow (5+ min) | First run, no cache | Normal. Use `--keep-alive` for sequential runs. |
| sentencepiece error | Missing from pip install | Added to onstart.sh. Already fixed. |
| Training output not streaming | Missing flush | Add `sys.stdout.flush()` after every print. |
