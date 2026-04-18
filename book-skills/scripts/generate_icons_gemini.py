"""Batch icon generation via Gemini Imagen API or Gemini native image generation.

Generates PNG icons for callout types (or any prompt list) using
Google's Imagen 4.0 model or Gemini's native image generation with
parallel requests.

Usage (Imagen engine, the default):
    python generate_icons_gemini.py                          # generate all missing callout icons
    python generate_icons_gemini.py --prompts prompts.json   # custom prompt file
    python generate_icons_gemini.py --list                   # show available callout types
    python generate_icons_gemini.py --types exercise,tip     # generate specific types only
    python generate_icons_gemini.py --model imagen-4.0-ultra-generate-001  # use ultra model

Usage (Gemini native image generation engine):
    python generate_icons_gemini.py --engine gemini          # use Gemini generateContent
    python generate_icons_gemini.py --engine gemini --batch  # use async batchGenerateContent
    python generate_icons_gemini.py --engine gemini --model gemini-2.5-flash-image

Flags:
    --engine          Engine to use: "imagen" (default) or "gemini"
    --batch           Use async batchGenerateContent endpoint (gemini engine only);
                      creates a server-side batch job and polls until complete
    --poll-interval   Seconds between batch status polls (default: 5)
    --batch-timeout   Maximum seconds to wait for batch completion (default: 600)
    --prompts         JSON file with custom prompts
    --types           Comma-separated callout types to generate
    --list            Show available callout types
    --model           Model name (defaults vary by engine)
    --output-dir      Output directory for icons
    --overwrite       Overwrite existing icons
    --workers         Number of parallel workers (imagen and gemini non-batch)

Requires GEMINI_API_KEY environment variable or .env.all file in book root.

Prompt file format (JSON):
    [
        {"name": "exercise", "prompt": "A 48x48 icon of a dumbbell...", "output": "styles/icons/callout-exercise.png"},
        ...
    ]
"""
import argparse
import base64
import concurrent.futures
import json
import os
import ssl
import sys
import time
import urllib.request
from pathlib import Path

# --- Configuration ---
BOOK_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_OUTPUT_DIR = BOOK_ROOT / "styles" / "icons"
DEFAULT_MODEL_IMAGEN = "imagen-4.0-generate-001"
DEFAULT_MODEL_GEMINI = "gemini-2.5-flash-image"
MAX_WORKERS = 5
ASPECT_RATIO = "1:1"

# Callout icon prompts (the 15 canonical types)
CALLOUT_PROMPTS = {
    "big-picture": "A 48x48 pixel icon of a compass pointing north, flat design, purple color #7c3aed, transparent background, minimal vector style, thick lines",
    "key-insight": "A 48x48 pixel icon of a glowing lightbulb with rays, flat design, green color #43a047, transparent background, minimal vector style",
    "note": "A 48x48 pixel icon of a memo pad with lines, flat design, blue color #1976d2, transparent background, minimal vector style",
    "warning": "A 48x48 pixel icon of a warning triangle with exclamation mark, flat design, amber color #f9a825, transparent background, minimal vector style",
    "practical-example": "A 48x48 pixel icon of a construction crane, flat design, steel blue color #5dade2, transparent background, minimal vector style",
    "fun-note": "A 48x48 pixel icon of a sparkle star, flat design, pink color #e91e63, transparent background, minimal vector style",
    "research-frontier": "A 48x48 pixel icon of a microscope, flat design, teal color #00897b, transparent background, minimal vector style",
    "algorithm": "A 48x48 pixel icon of a flowchart with three connected nodes, flat design, indigo color #5c6bc0, transparent background, minimal vector style",
    "tip": "A 48x48 pixel icon of a wrench combined with a lightbulb, flat design, cyan color #00acc1, transparent background, minimal vector style",
    "exercise": "A 48x48 pixel icon of a pencil writing on paper, flat design, deep orange color #e64a19, transparent background, minimal vector style",
    "key-takeaway": "A 48x48 pixel icon of a star with an upward arrow, flat design, gold color #f9a825, transparent background, minimal vector style",
    "library-shortcut": "A 48x48 pixel icon of a book with a lightning bolt bookmark, flat design, teal color #00897b, transparent background, minimal vector style",
    "pathway": "A 48x48 pixel icon of a forking path or road splitting into two, flat design, purple color #7e57c2, transparent background, minimal vector style",
    "self-check": "A 48x48 pixel icon of a checklist with checkmarks, flat design, indigo color #3949ab, transparent background, minimal vector style",
    "lab": "A 48x48 pixel icon of an Erlenmeyer flask with bubbles, flat design, teal green color #00897b, transparent background, minimal vector style",
}


def load_api_key():
    """Load Gemini API key from environment or .env.all file."""
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    env_file = BOOK_ROOT / ".env.all"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip()
    print("ERROR: GEMINI_API_KEY not found in environment or .env.all", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Imagen engine (predict endpoint)
# ---------------------------------------------------------------------------

def generate_image_imagen(api_key, model, prompt, output_path, ctx=None):
    """Generate a single image via Imagen predict API."""
    if ctx is None:
        ctx = ssl.create_default_context()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predict?key={api_key}"
    payload = json.dumps({
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1, "aspectRatio": ASPECT_RATIO},
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, context=ctx)
    result = json.loads(resp.read())
    img_b64 = result["predictions"][0]["bytesBase64Encoded"]
    img_bytes = base64.b64decode(img_b64)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(img_bytes)
    return str(output_path), len(img_bytes)


def batch_generate_imagen(api_key, model, tasks, max_workers=MAX_WORKERS):
    """Generate multiple images in parallel via Imagen predict API.

    tasks: list of (name, prompt, output_path)
    Returns: list of (name, output_path, size_bytes, elapsed_s, error)
    """
    ctx = ssl.create_default_context()
    results = []

    def worker(name, prompt, output_path):
        t0 = time.time()
        try:
            path, size = generate_image_imagen(api_key, model, prompt, output_path, ctx)
            return (name, path, size, time.time() - t0, None)
        except Exception as e:
            return (name, output_path, 0, time.time() - t0, str(e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(worker, name, prompt, out): name
            for name, prompt, out in tasks
        }
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    return sorted(results, key=lambda r: r[0])


# ---------------------------------------------------------------------------
# Gemini engine (generateContent / batchGenerateContent)
# ---------------------------------------------------------------------------

def _parse_gemini_image_from_parts(parts):
    """Extract base64 image data from a Gemini response parts list.

    Returns the raw image bytes, or raises ValueError if no image was found.
    """
    for part in parts:
        inline = part.get("inlineData")
        if inline and inline.get("data"):
            return base64.b64decode(inline["data"])
    raise ValueError("No inlineData image found in response parts")


def generate_image_gemini(api_key, model, prompt, output_path, ctx=None):
    """Generate a single image via Gemini generateContent endpoint."""
    if ctx is None:
        ctx = ssl.create_default_context()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={api_key}"
    )
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, context=ctx, timeout=120)
    result = json.loads(resp.read())

    parts = result["candidates"][0]["content"]["parts"]
    img_bytes = _parse_gemini_image_from_parts(parts)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(img_bytes)
    return str(output_path), len(img_bytes)


def batch_generate_gemini_single(api_key, model, tasks, max_workers=MAX_WORKERS):
    """Generate multiple images via parallel Gemini generateContent calls.

    tasks: list of (name, prompt, output_path)
    Returns: list of (name, output_path, size_bytes, elapsed_s, error)
    """
    ctx = ssl.create_default_context()
    results = []

    def worker(name, prompt, output_path):
        t0 = time.time()
        try:
            path, size = generate_image_gemini(api_key, model, prompt, output_path, ctx)
            return (name, path, size, time.time() - t0, None)
        except Exception as e:
            return (name, output_path, 0, time.time() - t0, str(e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(worker, name, prompt, out): name
            for name, prompt, out in tasks
        }
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    return sorted(results, key=lambda r: r[0])


def _poll_batch(api_key, batch_name, ctx, poll_interval=5, timeout=600):
    """Poll a batch operation until it completes or times out.

    Returns the final batch metadata dict.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/{batch_name}?key={api_key}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, context=ctx, timeout=30)
        data = json.loads(resp.read())
        # State lives inside metadata for the Operation wrapper
        meta = data.get("metadata", data)
        state = meta.get("state", "")
        stats = meta.get("batchStats", {})
        pending = int(stats.get("pendingRequestCount", "0"))
        total = int(stats.get("requestCount", "0"))
        done = total - pending
        print(f"  [batch] {state}: {done}/{total} complete", flush=True)
        if state in ("BATCH_STATE_SUCCEEDED", "BATCH_STATE_FAILED", "BATCH_STATE_CANCELLED"):
            return meta
        time.sleep(poll_interval)
    raise TimeoutError(f"Batch {batch_name} did not complete within {timeout}s")


def batch_generate_gemini_batch(api_key, model, tasks, poll_interval=5, timeout=600):
    """Generate multiple images via the async batchGenerateContent endpoint.

    Creates a batch job, polls until completion, then extracts the inline
    responses and saves each image.

    tasks: list of (name, prompt, output_path)
    Returns: list of (name, output_path, size_bytes, elapsed_s, error)
    """
    ctx = ssl.create_default_context()

    # Step 1: create the batch
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":batchGenerateContent?key={api_key}"
    )
    inline_requests = []
    for i, (_name, prompt, _out) in enumerate(tasks):
        inline_requests.append({
            "request": {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
            },
            "metadata": {"key": _name},
        })

    payload = json.dumps({
        "batch": {
            "displayName": f"icon-gen-{int(time.time())}",
            "inputConfig": {
                "requests": {
                    "requests": inline_requests,
                },
            },
        },
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    t0 = time.time()
    resp = urllib.request.urlopen(req, context=ctx, timeout=60)
    op = json.loads(resp.read())

    # The operation name is used to poll; batch name is inside metadata
    batch_name = op.get("metadata", {}).get("name", op.get("name", ""))
    if not batch_name:
        raise RuntimeError(f"Could not determine batch name from response: {json.dumps(op)[:500]}")
    print(f"  [batch] created: {batch_name}")

    # Step 2: poll until done
    meta = _poll_batch(api_key, batch_name, ctx, poll_interval=poll_interval, timeout=timeout)
    elapsed_total = time.time() - t0

    # Step 3: extract inline responses
    # The response structure nests as: output.inlinedResponses.inlinedResponses[]
    output = meta.get("output", {})
    inlined = output.get("inlinedResponses", {})
    responses = inlined.get("inlinedResponses", [])

    results = []
    for i, (name, prompt, output_path) in enumerate(tasks):
        try:
            if i >= len(responses):
                raise ValueError(f"No response at index {i}; got {len(responses)} responses total")
            entry = responses[i]
            # Individual responses may contain an error
            if "error" in entry:
                err = entry["error"]
                raise ValueError(f"API error: {err.get('message', str(err))}")
            resp_body = entry.get("response", entry)
            parts = resp_body["candidates"][0]["content"]["parts"]
            img_bytes = _parse_gemini_image_from_parts(parts)
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(img_bytes)
            results.append((name, str(output_path), len(img_bytes), elapsed_total, None))
        except Exception as e:
            results.append((name, str(output_path), 0, elapsed_total, str(e)))

    return sorted(results, key=lambda r: r[0])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Batch icon generation via Gemini Imagen or Gemini native image generation")
    parser.add_argument("--engine", choices=["imagen", "gemini"], default="imagen",
                        help="Generation engine: 'imagen' (Imagen predict API) or 'gemini' (generateContent with image output)")
    parser.add_argument("--batch", action="store_true",
                        help="Use async batchGenerateContent endpoint (gemini engine only)")
    parser.add_argument("--poll-interval", type=int, default=5,
                        help="Seconds between batch status polls (default: 5)")
    parser.add_argument("--batch-timeout", type=int, default=600,
                        help="Maximum seconds to wait for batch completion (default: 600)")
    parser.add_argument("--prompts", help="JSON file with custom prompts")
    parser.add_argument("--types", help="Comma-separated callout types to generate")
    parser.add_argument("--list", action="store_true", help="List available callout types")
    parser.add_argument("--model", default=None,
                        help="Model name (default: imagen-4.0-generate-001 for imagen, gemini-2.5-flash-image for gemini)")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory for icons")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing icons")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help=f"Parallel workers (default: {MAX_WORKERS})")
    args = parser.parse_args()

    # Resolve default model per engine
    if args.model is None:
        if args.engine == "gemini":
            args.model = DEFAULT_MODEL_GEMINI
        else:
            args.model = DEFAULT_MODEL_IMAGEN

    if args.list:
        print("Available callout types:")
        for name in sorted(CALLOUT_PROMPTS):
            icon_path = Path(args.output_dir) / f"callout-{name}.png"
            exists = "exists" if icon_path.exists() else "MISSING"
            print(f"  {name:20s} [{exists}]")
        return

    # Validate flag combinations
    if args.batch and args.engine != "gemini":
        print("ERROR: the --batch flag is only supported with --engine gemini", file=sys.stderr)
        sys.exit(1)

    # Build task list
    if args.prompts:
        with open(args.prompts) as f:
            custom = json.load(f)
        tasks = [(item["name"], item["prompt"], item.get("output", f"{args.output_dir}/callout-{item['name']}.png")) for item in custom]
    else:
        types_filter = set(args.types.split(",")) if args.types else None
        tasks = []
        for name, prompt in sorted(CALLOUT_PROMPTS.items()):
            if types_filter and name not in types_filter:
                continue
            output_path = Path(args.output_dir) / f"callout-{name}.png"
            if output_path.exists() and not args.overwrite:
                print(f"  SKIP {name} (exists, use --overwrite to regenerate)")
                continue
            tasks.append((name, prompt, str(output_path)))

    if not tasks:
        print("No icons to generate.")
        return

    api_key = load_api_key()

    mode_label = args.engine
    if args.engine == "gemini" and args.batch:
        mode_label = "gemini (batch)"

    print(f"Generating {len(tasks)} icon(s) with {args.model} via {mode_label}...")
    t0 = time.time()

    if args.engine == "imagen":
        results = batch_generate_imagen(api_key, args.model, tasks, max_workers=args.workers)
    elif args.engine == "gemini" and args.batch:
        results = batch_generate_gemini_batch(
            api_key, args.model, tasks,
            poll_interval=args.poll_interval, timeout=args.batch_timeout,
        )
    else:
        results = batch_generate_gemini_single(api_key, args.model, tasks, max_workers=args.workers)

    elapsed = time.time() - t0

    for name, path, size, dt, error in results:
        if error:
            print(f"  FAIL {name}: {error}")
        else:
            print(f"  OK   {name}: {size:,} bytes ({dt:.1f}s) -> {path}")

    ok = sum(1 for r in results if r[4] is None)
    fail = sum(1 for r in results if r[4] is not None)
    print(f"\nDone: {ok} generated, {fail} failed, {elapsed:.1f}s total")


if __name__ == "__main__":
    main()
