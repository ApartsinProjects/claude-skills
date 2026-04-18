"""
Audit content coverage across the book for three topic areas:
1. XAI / Interpretability / Attention Visualization
2. HPC / Distributed Frameworks (Databricks, Ray, etc.)
3. NLP Task Methods (classification, extraction, etc.)

Reports which chapters cover each topic and identifies gaps.
"""

import re
from pathlib import Path
from collections import defaultdict

ROOT = Path(r"E:\Projects\LLMCourse")
SKIP_DIRS = {"vendor", "node_modules", ".git", "__pycache__", "scripts", "agents", "_lab_fragments", "front-matter"}

# ── Topic 1: XAI / Interpretability ──────────────────────────────
XAI_PATTERNS = {
    "Attention visualization": r"attention\s+(?:vis|map|heatmap|head|pattern|weight)",
    "BertViz / ecco": r"bertviz|ecco\b",
    "SHAP": r"\bSHAP\b",
    "LIME": r"\bLIME\b",
    "Captum": r"\bCaptum\b",
    "Interpretability": r"interpretab|explainab",
    "Mechanistic interp": r"mechanistic\s+interpret|circuit\s+analysis|superposition",
    "Probing classifiers": r"probing\s+(?:classifier|task|experiment)",
    "Feature attribution": r"feature\s+attribut|saliency\s+map|gradient\s+attribut",
    "Activation patching": r"activation\s+patch|causal\s+trac",
    "Logit lens": r"logit\s+lens|tuned\s+lens",
    "XAI general": r"\bXAI\b|explainable\s+(?:AI|artificial)",
}

# ── Topic 2: HPC / Distributed ───────────────────────────────────
HPC_PATTERNS = {
    "Databricks": r"\bDatabricks\b",
    "Ray": r"\bRay\b(?:\s+(?:Train|Serve|Data|Tune))?",
    "Spark / PySpark": r"\bSpark\b|\bPySpark\b",
    "DeepSpeed": r"\bDeepSpeed\b",
    "FSDP": r"\bFSDP\b|FullyShardedDataParallel",
    "Megatron": r"\bMegatron\b",
    "Horovod": r"\bHorovod\b",
    "Data lake": r"data\s*lake|lakehouse|Delta\s+Lake",
    "Feature store": r"feature\s+store|Feast\b|Tecton\b",
    "Distributed training": r"distributed\s+(?:train|comput|process)",
    "Model parallelism": r"model\s+parallel|tensor\s+parallel|pipeline\s+parallel",
    "Data parallelism": r"data\s+parallel(?:ism)?",
    "Gradient accumulation": r"gradient\s+accumul",
    "Mixed precision": r"mixed\s+precision|fp16\b|bf16\b|half.precision",
    "vLLM / TGI": r"\bvLLM\b|text.generation.inference|\bTGI\b",
    "Model serving": r"model\s+serv|inference\s+(?:serv|optim|engine)",
}

# ── Topic 3: NLP Task Methods ────────────────────────────────────
NLP_PATTERNS = {
    "Text classification": r"text\s+classif|sentiment\s+(?:analy|classif)|topic\s+classif",
    "NER / Entity extraction": r"named\s+entity|NER\b|entity\s+(?:extract|recogn)",
    "Information extraction": r"information\s+extract|relation\s+extract",
    "Summarization": r"summariz|abstractive|extractive\s+summ",
    "Machine translation": r"machine\s+translat|neural\s+translat",
    "Question answering": r"question\s+answer|QA\s+(?:system|task|model)|reading\s+comprehension",
    "Text generation": r"text\s+generat(?!ion\s+inference)",
    "Semantic similarity": r"semantic\s+similar|sentence\s+similar|STS\b",
    "Zero-shot classification": r"zero.shot\s+classif",
    "Few-shot learning": r"few.shot\s+(?:learn|classif|prompt)",
    "Text-to-SQL": r"text.to.SQL|natural\s+language.to.SQL",
    "Code generation": r"code\s+generat|program\s+synth",
    "Structured output": r"structured\s+output|JSON\s+(?:mode|output|schema)",
    "Function calling": r"function\s+call|tool\s+(?:use|call)",
}

TOPIC_SETS = [
    ("XAI / Interpretability", XAI_PATTERNS),
    ("HPC / Distributed Frameworks", HPC_PATTERNS),
    ("NLP Task Methods with LLMs", NLP_PATTERNS),
]


def get_chapter_label(fpath: Path) -> str:
    """Extract a readable chapter label from path."""
    rel = fpath.relative_to(ROOT)
    parts = rel.parts
    # Find the module directory
    for p in parts:
        if p.startswith("module-") or p.startswith("appendix-"):
            return p
    if parts[0].startswith("part-"):
        return f"{parts[0]}/{parts[1]}" if len(parts) > 1 else parts[0]
    return str(rel)


def scan_file(fpath: Path, patterns: dict) -> dict:
    """Scan a file for pattern matches. Returns {pattern_name: count}."""
    try:
        text = fpath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {}

    # Strip HTML tags for cleaner matching
    clean = re.sub(r'<[^>]+>', ' ', text)

    hits = {}
    for name, pat in patterns.items():
        matches = re.findall(pat, clean, re.IGNORECASE)
        if matches:
            hits[name] = len(matches)
    return hits


def main():
    # Collect all HTML files grouped by chapter
    chapter_files = defaultdict(list)
    for fpath in sorted(ROOT.rglob("*.html")):
        parts = fpath.relative_to(ROOT).parts
        if any(p in SKIP_DIRS for p in parts):
            continue
        if fpath.name.startswith("_"):
            continue
        chapter = get_chapter_label(fpath)
        chapter_files[chapter].append(fpath)

    for topic_name, patterns in TOPIC_SETS:
        print(f"\n{'#'*70}")
        print(f"  TOPIC: {topic_name}")
        print(f"{'#'*70}\n")

        # Scan all chapters
        chapter_coverage = {}
        for chapter, files in sorted(chapter_files.items()):
            combined_hits = defaultdict(int)
            for f in files:
                hits = scan_file(f, patterns)
                for k, v in hits.items():
                    combined_hits[k] += v
            if combined_hits:
                chapter_coverage[chapter] = dict(combined_hits)

        if chapter_coverage:
            print(f"  Chapters with coverage ({len(chapter_coverage)}):")
            for ch, hits in sorted(chapter_coverage.items()):
                total = sum(hits.values())
                top_topics = sorted(hits.items(), key=lambda x: -x[1])[:5]
                topics_str = ", ".join(f"{k}({v})" for k, v in top_topics)
                print(f"    {ch}: {total} mentions [{topics_str}]")
        else:
            print("  NO COVERAGE FOUND!")

        # Report gaps
        uncovered = [name for name in patterns if not any(name in ch_hits for ch_hits in chapter_coverage.values())]
        if uncovered:
            print(f"\n  GAPS (subtopics with ZERO coverage):")
            for name in uncovered:
                print(f"    - {name}")

        print()


if __name__ == "__main__":
    main()
