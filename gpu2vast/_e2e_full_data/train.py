
import json, os, sys, time
print("[train] === GPU2Vast PyTorch + Transformers + TensorBoard ===")
sys.stdout.flush()

print("[train] Checking GPU...")
sys.stdout.flush()
os.system("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 'No GPU'")

print("[train] Loading model from HuggingFace...")
sys.stdout.flush()
dl_start = time.time()
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from torch.utils.tensorboard import SummaryWriter

model_name = "distilbert-base-uncased"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=3)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = model.to(device)
dl_time = time.time() - dl_start
print(f"[train] Model loaded: {model_name} ({sum(p.numel() for p in model.parameters()):,} params) on {device} in {dl_time:.1f}s")
sys.stdout.flush()

print("[train] Loading data...")
sys.stdout.flush()
with open("train.json") as f:
    data = json.load(f)
texts = [s["text"] for s in data]
labels = [s["label"] for s in data]
inputs = tokenizer(texts, padding=True, truncation=True, max_length=64, return_tensors="pt").to(device)
labels_t = torch.tensor(labels, device=device)
print(f"[train] Loaded {len(data)} samples")
sys.stdout.flush()

# TensorBoard writer
print("[train] Starting TensorBoard logging...")
sys.stdout.flush()
os.makedirs("runs", exist_ok=True)
writer = SummaryWriter(log_dir="runs")

print("[train] Training (15 steps)...")
sys.stdout.flush()
optimizer = torch.optim.AdamW(model.parameters(), lr=5e-5)
model.train()
log = []

for step in range(1, 16):
    outputs = model(**inputs, labels=labels_t)
    loss = outputs.loss
    loss.backward()
    optimizer.step()
    optimizer.zero_grad()

    loss_val = loss.item()
    writer.add_scalar("train/loss", loss_val, step)
    writer.add_scalar("train/lr", 5e-5, step)
    writer.flush()

    log.append({"step": step, "total": 15, "loss": round(loss_val, 4)})
    print(f"  {step}/15 loss={loss_val:.4f}")
    sys.stdout.flush()
    time.sleep(0.3)

# Evaluate
print("[train] Evaluating...")
sys.stdout.flush()
model.eval()
with torch.no_grad():
    outputs = model(**inputs, labels=labels_t)
    eval_loss = outputs.loss.item()
    preds = outputs.logits.argmax(dim=-1)
    accuracy = (preds == labels_t).float().mean().item()
writer.add_scalar("eval/loss", eval_loss, 15)
writer.add_scalar("eval/accuracy", accuracy, 15)
writer.flush()
writer.close()
print(f"[train] Eval: loss={eval_loss:.4f}, accuracy={accuracy:.4f}")
sys.stdout.flush()

# Save
print("[train] Saving model + results...")
sys.stdout.flush()
os.makedirs("results/model_weights", exist_ok=True)
model.save_pretrained("results/model_weights")
tokenizer.save_pretrained("results/model_weights")

with open("results/training_log.json", "w") as f:
    json.dump(log, f, indent=2)

weight_files = os.listdir("results/model_weights")
total_size = sum(os.path.getsize(f"results/model_weights/{f}") for f in weight_files)

summary = {
    "framework": "pytorch",
    "model": model_name,
    "device": str(device),
    "param_count": sum(p.numel() for p in model.parameters()),
    "samples": len(data),
    "steps": 15,
    "initial_loss": log[0]["loss"],
    "final_loss": log[-1]["loss"],
    "eval_loss": round(eval_loss, 4),
    "eval_accuracy": round(accuracy, 4),
    "loss_decreased": log[-1]["loss"] < log[0]["loss"],
    "model_download_time_s": round(dl_time, 1),
    "weight_files": weight_files,
    "total_weight_size_bytes": total_size,
    "tensorboard_dir": "runs",
}
with open("results/summary.json", "w") as f:
    json.dump(summary, f, indent=2)

# Also copy TensorBoard runs to results for download
import shutil
if os.path.exists("runs"):
    shutil.copytree("runs", "results/tensorboard_runs", dirs_exist_ok=True)

print(f"[train] Saved {len(weight_files)} weight files ({total_size:,} bytes)")
print(f"[train] Loss: {log[0]['loss']:.4f} -> {log[-1]['loss']:.4f}")
print(f"[train] TensorBoard logs in runs/")
print("[train] === DONE ===")
sys.stdout.flush()
