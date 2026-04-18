"""Tiny GPT-2 generative model test for GPU2Vast validation.
Fine-tunes distilgpt2 on a few lines of text for causal language modeling.
"""
import sys
import os
import json
import time
import torch
from torch.utils.tensorboard import SummaryWriter
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    DataCollatorForLanguageModeling,
)
from torch.utils.data import DataLoader

assert torch.cuda.is_available(), "CUDA not available. This script requires a GPU."
device = torch.device("cuda")
print(f"[train] GPU: {torch.cuda.get_device_name(0)}"); sys.stdout.flush()

writer = SummaryWriter(log_dir="runs")
t0 = time.time()

writer.add_text("phase", "model_download: loading distilgpt2", 0)
writer.flush()
print("[train] Loading distilgpt2 tokenizer and model..."); sys.stdout.flush()
tokenizer = AutoTokenizer.from_pretrained("distilgpt2")
tokenizer.pad_token = tokenizer.eos_token
model = AutoModelForCausalLM.from_pretrained("distilgpt2")
model.to(device)
param_count = sum(p.numel() for p in model.parameters())
writer.add_text("phase", f"model_loaded: distilgpt2 ({param_count:,} params) on {device}", 0)
print(f"[train] Model loaded: distilgpt2 ({param_count:,} params) on {device}"); sys.stdout.flush()

writer.add_text("phase", "data_loading: tokenizing training texts", 0)
texts = [
    "The old lighthouse keeper watched the storm roll in from the west.",
    "Every morning she would walk along the shore collecting sea glass.",
    "The village had not changed much in the last hundred years.",
    "Stars filled the sky like scattered diamonds on dark velvet.",
    "He opened the dusty book and began to read aloud to the children.",
    "Rain drummed steadily on the tin roof while they played cards.",
    "The garden was overgrown but still beautiful in its wild way.",
    "She smiled at the stranger and offered him a cup of warm tea.",
]

print(f"[train] Tokenizing {len(texts)} sentences..."); sys.stdout.flush()
encodings = tokenizer(
    texts, truncation=True, padding="max_length", max_length=48, return_tensors="pt"
)
writer.add_text("phase", f"data_loaded: {len(texts)} samples tokenized (max_length=48)", 0)

class TextDataset(torch.utils.data.Dataset):
    def __init__(self, encodings):
        self.input_ids = encodings["input_ids"]
        self.attention_mask = encodings["attention_mask"]
    def __len__(self):
        return len(self.input_ids)
    def __getitem__(self, idx):
        return {"input_ids": self.input_ids[idx], "attention_mask": self.attention_mask[idx],
                "labels": self.input_ids[idx].clone()}

dataset = TextDataset(encodings)
loader = DataLoader(dataset, batch_size=4, shuffle=True)

lr = 5e-4
optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
epochs = 20
total_steps = epochs * len(loader)

writer.add_text("phase", f"training_start: {total_steps} steps, {epochs} epochs, lr={lr}", 0)
writer.flush()
print(f"[train] Training ({total_steps} steps, {epochs} epochs)..."); sys.stdout.flush()
model.train()
start_time = time.time()
step = 0

for epoch in range(1, epochs + 1):
    writer.add_text("phase", f"epoch_start: epoch {epoch}/{epochs}", epoch)
    epoch_loss = 0.0
    batch_count = 0
    for batch in loader:
        step += 1
        batch = {k: v.to(device) for k, v in batch.items()}
        outputs = model(**batch)
        loss = outputs.loss
        loss.backward()
        optimizer.step()
        optimizer.zero_grad()
        epoch_loss += loss.item()
        batch_count += 1
        writer.add_scalar("train/loss", loss.item(), step)
        print(f"  {step}/{total_steps} loss={loss.item():.4f} epoch={epoch}"); sys.stdout.flush()
    avg_loss = epoch_loss / batch_count
    writer.add_scalar("train/epoch_loss", avg_loss, epoch)
    writer.add_text("phase", f"epoch_end: epoch {epoch}/{epochs}, avg_loss={avg_loss:.4f}", epoch)
    print(f"[train] Epoch {epoch} avg_loss={avg_loss:.4f}"); sys.stdout.flush()

elapsed = time.time() - start_time
writer.add_text("phase", f"training_complete: {elapsed:.1f}s, {total_steps} steps", epochs)
print(f"[train] Training complete in {elapsed:.1f}s"); sys.stdout.flush()

writer.add_text("phase", "eval_start: computing perplexity + generating sample text", epochs)
model.eval()
with torch.no_grad():
    total_eval_loss = 0.0
    eval_batches = 0
    for batch in loader:
        batch = {k: v.to(device) for k, v in batch.items()}
        outputs = model(**batch)
        total_eval_loss += outputs.loss.item()
        eval_batches += 1
    avg_eval_loss = total_eval_loss / eval_batches
    perplexity = torch.exp(torch.tensor(avg_eval_loss)).item()

writer.add_scalar("eval/loss", avg_eval_loss, epochs)
writer.add_scalar("eval/perplexity", perplexity, epochs)

prompts = ["The old lighthouse", "Every morning she", "Stars filled the"]
generated_samples = []
for prompt in prompts:
    input_ids = tokenizer.encode(prompt, return_tensors="pt").to(device)
    with torch.no_grad():
        output = model.generate(
            input_ids, max_new_tokens=30, do_sample=True,
            temperature=0.8, top_p=0.9, pad_token_id=tokenizer.eos_token_id,
        )
    text = tokenizer.decode(output[0], skip_special_tokens=True)
    generated_samples.append(text)
    print(f"[train] Generated: {text}"); sys.stdout.flush()

writer.add_text("generated", "\n\n".join(f"**{p}**: {s}" for p, s in zip(prompts, generated_samples)), epochs)
writer.add_text("phase", f"eval_complete: loss={avg_eval_loss:.4f}, perplexity={perplexity:.2f}", epochs)
print(f"[train] Eval: loss={avg_eval_loss:.4f}, perplexity={perplexity:.2f}"); sys.stdout.flush()

writer.add_text("phase", "saving_results: model + summary to results/", epochs)
os.makedirs("results/model", exist_ok=True)
summary = {
    "model": "distilgpt2",
    "params": param_count,
    "device": str(device),
    "epochs": epochs,
    "total_steps": total_steps,
    "lr": lr,
    "final_loss": loss.item(),
    "eval_loss": avg_eval_loss,
    "perplexity": perplexity,
    "elapsed_seconds": elapsed,
    "num_texts": len(texts),
    "generated_samples": generated_samples,
}
with open("results/summary.json", "w") as f:
    json.dump(summary, f, indent=2)

model.save_pretrained("results/model")
tokenizer.save_pretrained("results/model")
writer.add_text("phase", f"done: distilgpt2 fine-tuned, {elapsed:.1f}s, perplexity={perplexity:.2f}", epochs)
writer.close()
print(f"[train] Saved model to results/model/"); sys.stdout.flush()
print("[train] === DONE ==="); sys.stdout.flush()
