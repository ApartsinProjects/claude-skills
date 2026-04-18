import json, os, sys, time
print("[train] === Sentiment Classification with bert-tiny ===")
sys.stdout.flush()

print("[train] Checking GPU...")
sys.stdout.flush()
os.system("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 'No GPU'")

print("[train] Loading bert-tiny from HuggingFace...")
sys.stdout.flush()
t0 = time.time()
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from torch.utils.tensorboard import SummaryWriter

model_name = "prajjwal1/bert-tiny"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=3)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = model.to(device)
params = sum(p.numel() for p in model.parameters())
print(f"[train] Loaded {model_name} ({params:,} params) on {device} in {time.time()-t0:.1f}s")
sys.stdout.flush()

print("[train] Loading data...")
sys.stdout.flush()
with open("sentiment.json") as f:
    data = json.load(f)
texts = [s["text"] for s in data]
labels = [s["label"] for s in data]
inputs = tokenizer(texts, padding=True, truncation=True, max_length=64, return_tensors="pt").to(device)
labels_t = torch.tensor(labels, device=device)
print(f"[train] {len(data)} samples loaded")
sys.stdout.flush()

os.makedirs("runs", exist_ok=True)
writer = SummaryWriter(log_dir="runs")

print("[train] Training (20 steps)...")
sys.stdout.flush()
optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4)
model.train()
log = []
for step in range(1, 21):
    out = model(**inputs, labels=labels_t)
    loss = out.loss
    loss.backward()
    optimizer.step()
    optimizer.zero_grad()
    lv = loss.item()
    writer.add_scalar("train/loss", lv, step)
    log.append({"step": step, "loss": round(lv, 4)})
    print(f"  {step}/20 loss={lv:.4f}")
    sys.stdout.flush()
    time.sleep(0.2)

model.eval()
with torch.no_grad():
    out = model(**inputs, labels=labels_t)
    acc = (out.logits.argmax(-1) == labels_t).float().mean().item()
writer.add_scalar("eval/accuracy", acc, 20)
writer.close()
print(f"[train] Eval accuracy: {acc:.4f}")
sys.stdout.flush()

os.makedirs("results", exist_ok=True)
model.save_pretrained("results/model")
tokenizer.save_pretrained("results/model")
with open("results/log.json", "w") as f:
    json.dump(log, f, indent=2)
with open("results/summary.json", "w") as f:
    json.dump({"model": model_name, "params": params, "steps": 20,
               "initial_loss": log[0]["loss"], "final_loss": log[-1]["loss"],
               "accuracy": round(acc, 4), "device": str(device)}, f, indent=2)

import shutil
if os.path.exists("runs"):
    shutil.copytree("runs", "results/tb_runs", dirs_exist_ok=True)

print(f"[train] Loss: {log[0]['loss']:.4f} -> {log[-1]['loss']:.4f}")
print("[train] === DONE ===")
sys.stdout.flush()
