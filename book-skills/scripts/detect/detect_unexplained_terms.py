"""
Detect technical terms that appear in sections without being:
1. Explained in that section (defined, described)
2. Hyperlinked to another section where they are explained

This finds terms used in isolation without context for the reader.
"""

import re
from pathlib import Path
from collections import defaultdict

BASE = Path(r"E:\Projects\LLMCourse")
EXCLUDE_DIRS = {"_scripts_archive", "node_modules", ".claude", "scripts", "templates", "styles", "agents", "_lab_fragments"}

# Key technical terms that should be explained or cross-referenced
TERMS = [
    # Core ML
    "gradient descent", "backpropagation", "loss function", "cross-entropy",
    "softmax", "sigmoid", "ReLU", "dropout", "batch normalization",
    "layer normalization", "learning rate", "weight decay", "Adam optimizer",
    # Transformer specific
    "attention mechanism", "self-attention", "multi-head attention",
    "positional encoding", "feed-forward network", "residual connection",
    "layer norm", "RMSNorm", "KV cache", "Flash Attention", "FlashAttention",
    # LLM specific
    "tokenization", "BPE", "byte pair encoding", "SentencePiece",
    "temperature", "top-k", "top-p", "nucleus sampling",
    "beam search", "greedy decoding", "perplexity",
    "fine-tuning", "transfer learning", "few-shot", "zero-shot",
    "in-context learning", "chain-of-thought", "prompt engineering",
    # Training
    "LoRA", "QLoRA", "PEFT", "adapter", "quantization",
    "RLHF", "DPO", "PPO", "reward model", "preference learning",
    "knowledge distillation", "model merging", "SLERP",
    "catastrophic forgetting", "continual learning",
    # Retrieval
    "embedding", "vector database", "cosine similarity",
    "RAG", "retrieval-augmented generation", "chunking",
    "HNSW", "semantic search", "BM25", "reranking",
    # Agents
    "ReAct", "function calling", "tool use", "MCP",
    "multi-agent", "planning", "chain-of-thought",
    # Eval
    "BLEU", "ROUGE", "BERTScore", "perplexity",
    "human evaluation", "LLM-as-judge",
]

def find_section_files():
    files = []
    for f in BASE.rglob("*.html"):
        if any(part in EXCLUDE_DIRS for part in f.parts):
            continue
        if f.name.startswith("section-") or (f.name == "index.html" and f.parent.name.startswith("module-")):
            files.append(f)
    return sorted(files)

def check_file(filepath):
    text = filepath.read_text(encoding="utf-8")
    # Strip HTML tags for text analysis
    plain = re.sub(r'<[^>]+>', ' ', text)
    plain = re.sub(r'&\w+;', ' ', plain)
    plain = re.sub(r'\s+', ' ', plain)

    # Check which terms appear
    found_terms = []
    for term in TERMS:
        pattern = re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)
        if pattern.search(plain):
            # Check if it's hyperlinked (has <a> around it)
            link_pattern = re.compile(
                r'<a[^>]+href="[^"]*"[^>]*>[^<]*' + re.escape(term) + r'[^<]*</a>',
                re.IGNORECASE
            )
            is_linked = bool(link_pattern.search(text))

            # Count occurrences
            count = len(pattern.findall(plain))

            found_terms.append({
                "term": term,
                "count": count,
                "linked": is_linked,
            })

    return found_terms

def main():
    files = find_section_files()
    print(f"Scanning {len(files)} section files for technical term usage...\n")

    # Track which terms are used but never linked
    term_link_stats = defaultdict(lambda: {"total_files": 0, "linked_files": 0, "unlinked_files": []})

    for f in files:
        terms = check_file(f)
        rel = str(f.relative_to(BASE))
        for t in terms:
            stats = term_link_stats[t["term"]]
            stats["total_files"] += 1
            if t["linked"]:
                stats["linked_files"] += 1
            else:
                stats["unlinked_files"].append(rel)

    # Report terms that appear in many files but are rarely linked
    print("TERMS USED BUT RARELY CROSS-REFERENCED:")
    print("=" * 70)
    results = []
    for term, stats in term_link_stats.items():
        if stats["total_files"] >= 5:  # Only report terms used in 5+ files
            link_pct = stats["linked_files"] / stats["total_files"] * 100
            results.append((term, stats["total_files"], stats["linked_files"], link_pct))

    results.sort(key=lambda x: x[3])  # Sort by link percentage (lowest first)

    for term, total, linked, pct in results[:40]:
        print(f"  {term}: used in {total} files, linked in {linked} ({pct:.0f}%)")

    print(f"\n\nTOTAL: {len(results)} terms tracked across {len(files)} files")

if __name__ == "__main__":
    main()
