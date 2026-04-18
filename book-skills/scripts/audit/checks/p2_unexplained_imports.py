"""Flag Python imports in code blocks that are not mentioned in nearby prose."""
import re
from collections import namedtuple

PRIORITY = "P2"
CHECK_ID = "UNEXPLAINED_IMPORT"
DESCRIPTION = "Python import in code block is not explained in surrounding prose"

Issue = namedtuple("Issue", ["priority", "check_id", "filepath", "line", "message"])

# Standard library modules that need no explanation in a textbook
STDLIB_SKIP = frozenset({
    "os", "sys", "re", "json", "math", "typing", "dataclasses", "pathlib",
    "collections", "functools", "itertools", "abc", "enum", "datetime",
    "time", "hashlib", "base64", "io", "copy", "warnings", "logging",
    "unittest", "argparse", "textwrap", "contextlib", "subprocess",
    "tempfile", "uuid", "random", "csv", "pickle", "struct", "socket",
    "http", "urllib", "string", "pprint", "glob", "shutil", "traceback",
    "inspect", "operator", "decimal", "fractions", "statistics", "asyncio",
    "concurrent", "threading", "multiprocessing", "signal", "dataclass",
    "types", "secrets", "pdb", "dis", "ast", "token", "tokenize",
    "builtins", "__future__",
})

# Common ML/data-science imports that readers are assumed to know
ML_SKIP = frozenset({
    "numpy", "np", "torch", "nn", "pandas", "pd",
    "matplotlib", "plt", "sklearn", "scipy",
    "pil", "pillow", "sqlite3", "difflib", "struct",
    "ipython", "ipywidgets", "notebook",
})

# Core LLM ecosystem libraries ubiquitous in this textbook
LLM_CORE_SKIP = frozenset({
    "openai", "anthropic", "transformers", "tokenizers", "datasets",
    "huggingface_hub", "accelerate", "safetensors", "evaluate",
    "sentence_transformers", "langchain", "langchain_core",
    "langchain_openai", "langchain_community", "langchain_text_splitters",
    "langchain_anthropic", "langchain_chroma", "langchain_experimental",
    "langgraph", "llama_index", "semantic_kernel",
    "peft", "trl", "bitsandbytes", "auto_gptq",
    "tiktoken", "sentencepiece",
    "pydantic", "fastapi", "uvicorn", "httpx", "requests", "aiohttp",
    "tqdm", "rich", "dotenv", "PIL", "pillow",
    "gradio", "streamlit",
    "chromadb", "pinecone", "qdrant_client", "weaviate", "faiss",
    "wandb", "mlflow", "comet_ml",
    "vllm", "litellm", "instructor",
})

ALL_SKIP = STDLIB_SKIP | ML_SKIP | LLM_CORE_SKIP

# Regex for import statements (captures the top-level module)
IMPORT_RE = re.compile(
    r"^\s*import\s+([\w.]+)"
    r"|"
    r"^\s*from\s+([\w.]+)\s+import"
)

# Detect code blocks: <pre><code ...> ... </code></pre>  or  <code class="language-python">
CODE_OPEN_RE = re.compile(
    r"<pre>\s*<code\b[^>]*>|<code\s+class\s*=\s*[\"']language-python[\"'][^>]*>",
    re.IGNORECASE,
)
CODE_CLOSE_RE = re.compile(r"</code>", re.IGNORECASE)

PROSE_RADIUS = 50  # lines before/after the code block to search for mention


def _extract_imports(code_lines):
    """Return list of (relative_line_offset, import_statement, library_name)."""
    results = []
    for offset, line in enumerate(code_lines):
        m = IMPORT_RE.match(line)
        if m:
            lib = (m.group(1) or m.group(2)).split(".")[0]
            results.append((offset, line.strip(), lib))
    return results


def _strip_tags(text):
    """Remove HTML tags so we can search for library names in prose."""
    return re.sub(r"<[^>]+>", " ", text).lower()


def run(filepath, html, context):
    issues = []
    lines = html.split("\n")
    total = len(lines)

    i = 0
    while i < total:
        m_open = CODE_OPEN_RE.search(lines[i])
        if not m_open:
            i += 1
            continue

        code_start = i
        # Collect code block lines until closing tag
        code_lines = []
        # The opening tag line may contain code after the tag
        first_line = lines[i][m_open.end():]
        in_block = True
        j = i

        while j < total:
            text = lines[j] if j != i else first_line
            m_close = CODE_CLOSE_RE.search(text)
            if m_close:
                code_lines.append(text[:m_close.start()])
                in_block = False
                break
            code_lines.append(text)
            j += 1

        code_end = j
        if in_block:
            # Never found closing tag; skip
            i += 1
            continue

        imports = _extract_imports(code_lines)
        if not imports:
            i = code_end + 1
            continue

        # Build prose window (excluding the code block itself)
        prose_start = max(0, code_start - PROSE_RADIUS)
        prose_end = min(total, code_end + PROSE_RADIUS + 1)
        prose_before = _strip_tags("\n".join(lines[prose_start:code_start]))
        prose_after = _strip_tags("\n".join(lines[code_end + 1:prose_end]))
        prose = prose_before + " " + prose_after

        for offset, stmt, lib in imports:
            if lib.lower() in ALL_SKIP:
                continue
            # Check if library name appears in prose (case-insensitive)
            if lib.lower() in prose:
                continue
            line_num = code_start + offset + 1
            issues.append(Issue(
                priority=PRIORITY,
                check_id=CHECK_ID,
                filepath=filepath,
                line=line_num,
                message=f"Import '{stmt}' : library '{lib}' not mentioned in nearby prose",
            ))

        i = code_end + 1

    return issues
