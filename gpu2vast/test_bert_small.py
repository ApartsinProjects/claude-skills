"""Minimal BERT training test for GPU2Vast validation.
Trains a tiny DistilBERT on masked language modeling with 5 sentences.
Should complete in under 2 minutes on any GPU.
"""
import sys
import os
import json
import time
import torch
from torch.utils.tensorboard import SummaryWriter
from transformers import (
    DistilBertTokenizer,
    DistilBertForMaskedLM,
    DataCollatorForLanguageModeling,
)
from torch.utils.data import DataLoader

writer = SummaryWriter(log_dir="runs")
t0 = time.time()

writer.add_text("phase", "model_download: loading distilbert-base-uncased", 0)
print("[train] Loading DistilBERT tokenizer and model..."); sys.stdout.flush()
tokenizer = DistilBertTokenizer.from_pretrained("distilbert-base-uncased")
model = DistilBertForMaskedLM.from_pretrained("distilbert-base-uncased")

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
writer.add_text("phase", f"model_loaded: distilbert-base-uncased on {device}", 0)
print(f"[train] Model on {device}"); sys.stdout.flush()

writer.add_text("phase", "data_loading: tokenizing training texts", 0)
texts = [
    "The cat sat on the mat and watched the birds outside.",
    "Machine learning models can learn patterns from data.",
    "Natural language processing helps computers understand text.",
    "Transformers use attention mechanisms for sequence modeling.",
    "Fine-tuning adapts pre-trained models to specific tasks.",
]

print(f"[train] Tokenizing {len(texts)} sentences..."); sys.stdout.flush()
encodings = tokenizer(texts, truncation=True, padding=True, max_length=64, return_tensors="pt")
writer.add_text("phase", f"data_loaded: {len(texts)} samples tokenized", 0)

class SimpleDataset(torch.utils.data.Dataset):
    def __init__(self, encodings):
        self.encodings = encodings
    def __len__(self):
        return len(self.encodings["input_ids"])
    def __getitem__(self, idx):
        return {k: v[idx] for k, v in self.encodings.items()}

dataset = SimpleDataset(encodings)
collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=True, mlm_probability=0.15)
loader = DataLoader(dataset, batch_size=2, shuffle=True, collate_fn=collator)

optimizer = torch.optim.AdamW(model.parameters(), lr=5e-5)
epochs = 10
total_steps = epochs * len(loader)

writer.add_text("phase", f"training_start: {total_steps} steps, {epochs} epochs, lr=5e-5", 0)
writer.flush()
print(f"[train] Training ({total_steps} steps, {epochs} epochs)..."); sys.stdout.flush()
model.train()
start_time = time.time()
step = 0

for epoch in range(1, epochs + 1):
    writer.add_text("phase", f"epoch_start: epoch {epoch}/{epochs}", epoch)
    epoch_loss = 0.0
    for batch in loader:
        step += 1
        batch = {k: v.to(device) for k, v in batch.items()}
        outputs = model(**batch)
        loss = outputs.loss
        loss.backward()
        optimizer.step()
        optimizer.zero_grad()
        epoch_loss += loss.item()
        writer.add_scalar("train/loss", loss.item(), step)
        print(f"  {step}/{total_steps} loss={loss.item():.4f} epoch={epoch}"); sys.stdout.flush()
    avg_loss = epoch_loss / len(loader)
    writer.add_scalar("train/epoch_loss", avg_loss, epoch)
    writer.add_text("phase", f"epoch_end: epoch {epoch}/{epochs}, avg_loss={avg_loss:.4f}", epoch)
    print(f"[train] Epoch {epoch} avg_loss={avg_loss:.4f}"); sys.stdout.flush()

elapsed = time.time() - start_time
writer.add_text("phase", f"training_complete: {elapsed:.1f}s, {total_steps} steps", epochs)
print(f"[train] Training complete in {elapsed:.1f}s"); sys.stdout.flush()

writer.add_text("phase", "eval_start: computing perplexity on training data", epochs)
model.eval()
with torch.no_grad():
    total_eval_loss = 0.0
    for batch in loader:
        batch = {k: v.to(device) for k, v in batch.items()}
        outputs = model(**batch)
        total_eval_loss += outputs.loss.item()
    avg_eval_loss = total_eval_loss / len(loader)
    perplexity = torch.exp(torch.tensor(avg_eval_loss)).item()

writer.add_scalar("eval/loss", avg_eval_loss, epochs)
writer.add_scalar("eval/perplexity", perplexity, epochs)
writer.add_text("phase", f"eval_complete: loss={avg_eval_loss:.4f}, perplexity={perplexity:.2f}", epochs)
print(f"[train] Eval: loss={avg_eval_loss:.4f}, perplexity={perplexity:.2f}"); sys.stdout.flush()

writer.add_text("phase", "saving_results: model + summary to results/", epochs)
os.makedirs("results", exist_ok=True)
summary = {
    "model": "distilbert-base-uncased",
    "device": str(device),
    "epochs": epochs,
    "total_steps": total_steps,
    "final_loss": loss.item(),
    "eval_loss": avg_eval_loss,
    "perplexity": perplexity,
    "elapsed_seconds": elapsed,
    "num_texts": len(texts),
}
with open("results/summary.json", "w") as f:
    json.dump(summary, f, indent=2)

model.save_pretrained("results/model")
tokenizer.save_pretrained("results/model")
writer.add_text("phase", f"done: saved model ({len(texts)} texts, {elapsed:.1f}s, perplexity={perplexity:.2f})", epochs)
writer.close()
print(f"[train] Saved model to results/model/"); sys.stdout.flush()
print("[train] === DONE ==="); sys.stdout.flush()
