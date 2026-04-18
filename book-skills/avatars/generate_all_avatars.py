#!/usr/bin/env python3
"""Generate avatar images for all 42 agents using Gemini Batch API (50% cost)."""

import base64
import json
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR

# Agent definitions: (filename, character description)
AGENTS = [
    ("00-chapter-lead", "a confident Latino male project manager named Alex with short dark hair, warm smile, wearing a modern blazer, holding a clipboard"),
    ("01-curriculum-alignment", "an East Asian female professor named Maya with glasses, short bob haircut, wearing a lab coat, holding a checklist with green checkmarks"),
    ("02-deep-explanation", "a distinguished older white male professor named Elias with a grey beard, tweed jacket, holding a magnifying glass over a book"),
    ("03-teaching-flow", "a Black female educator named Sana with natural hair, bright scarf, drawing a flowchart on a whiteboard with colorful arrows"),
    ("04-student-advocate", "a young gender-neutral person named Jamie with curly hair, casual hoodie, raising their hand like a student asking questions"),
    ("05-cognitive-load", "a South Asian female neuroscientist named Aisha with long dark hair, wearing a white coat, balancing blocks labeled 'memory' on a scale"),
    ("06-example-analogy", "a Latina female storyteller named Lina with wavy hair, colorful blouse, juggling different objects (lightbulb, gear, puzzle piece) as metaphors"),
    ("07-exercise-designer", "a muscular Black male trainer named Marcus with a whistle around his neck, holding a set of progressively harder puzzle pieces"),
    ("08-code-pedagogy", "a Japanese male developer named Kai with spiky hair, wearing a dark hoodie with code symbols, holding a glowing laptop"),
    ("09-visual-learning", "an Indian female designer named Priya with a bindi, colorful sari, painting a diagram on a canvas with bright colors"),
    ("10-misconception-analyst", "a white male detective named Leo with a deerstalker hat, holding a red 'X' stamp and a green checkmark, looking skeptical"),
    ("11-fact-integrity", "a Latina female fact-checker named Ruth with reading glasses on a chain, holding a thick reference book and a red pen"),
    ("12-terminology-keeper", "a Japanese male librarian named Kenji with neat hair, round glasses, organizing labeled cards in a filing cabinet"),
    ("13-cross-reference", "a Russian female architect named Elena with a hard hat, connecting nodes on a blueprint with colorful lines"),
    ("14-narrative-continuity", "a white female editor named Olivia with auburn hair in a bun, reading glasses, weaving threads of different colors together"),
    ("15-style-voice", "a British male editor named Max with a waistcoat, bow tie, holding a fountain pen and a style guide book"),
    ("16-engagement-designer", "an Indian male game designer named Ravi with a headset, colorful shirt, holding sparklers and confetti cannons"),
    ("17-senior-editor", "a Korean female senior editor named Catherine with silver-streaked hair, elegant jacket, red pen behind her ear, looking authoritative"),
    ("18-research-scientist", "a Scandinavian female researcher named Ingrid with braided blonde hair, lab goggles on forehead, holding scientific papers"),
    ("19-structural-architect", "a Swedish male architect named Henrik with a hard hat and rolled-up blueprints, standing next to a building framework"),
    ("20-content-update-scout", "a mixed-race female scout named Harper with binoculars, explorer hat, carrying a newspaper with 'BREAKING' headline"),
    ("21-self-containment-verifier", "a Nordic male inspector named Tomas with a clipboard, wearing a safety vest, checking items off a containment checklist"),
    ("22-opening-hook-designer", "a British-Nigerian female copywriter named Zara with bold earrings, holding a neon sign that says 'WOW'"),
    ("23-project-catalyst", "a non-binary person named Jordan with a tool belt, holding a rocket and a wrench, wearing safety goggles on forehead"),
    ("24-aha-moment-engineer", "a Japanese female inventor named Yuki with wild hair (like just had an idea), lightbulb glowing above her head"),
    ("25-visual-identity-director", "a French female art director named Ines with a beret, holding a color palette and a ruler, inspecting a canvas critically"),
    ("26-demo-simulation-designer", "a Brazilian male engineer named Rio with safety goggles, building a miniature working machine with gears and levers"),
    ("27-memorability-designer", "a Finnish female memory artist named Mika with a mind palace floating around her head, holding a sticky note with a mnemonic"),
    ("28-skeptical-reader", "a stern but fair white male critic named Victor with a monocle, arms crossed, one eyebrow raised, holding a red 'PROVE IT' sign"),
    ("29-prose-clarity-editor", "a friendly white female teacher named Clara with bright eyes, erasing complicated text from a chalkboard and writing simpler words"),
    ("30-readability-pacing-editor", "a Latino male chef named Sam slicing a large block of text into bite-sized pieces with a precision knife"),
    ("31-illustrator", "a French female artist named Iris with paint-stained apron, wild colorful hair, surrounded by floating illustrations and paintbrushes"),
    ("32-epigraph-writer", "a British male poet named Quentin with a quill pen, sitting in a leather armchair, chuckling at his own witty writing"),
    ("33-application-example", "a Nigerian female business consultant named Nadia with a blazer, holding case study folders, standing in front of industry charts"),
    ("34-fun-injector", "a charismatic mixed-race male comedian named Ziggy with wild curly hair, colorful suspenders, holding a rubber chicken in one hand and a textbook in the other, winking"),
    ("35-bibliography", "a distinguished older white female librarian named Margot with silver hair in a French twist, reading glasses on a chain, surrounded by floating hyperlinked book spines and glowing citation marks"),
    ("36-meta-agent", "a sharp-eyed Middle Eastern female auditor named Audra with dark hair in a sleek bun, wearing a tailored charcoal suit, holding a magnifying glass over a grid of agent report cards, with green and red marks visible"),
    ("37-controller", "a commanding white male director named Morgan with silver temples, dark suit, holding a conductor's baton, orchestrating a wall of agent status screens"),
    ("38-publication-qa", "a meticulous white male inspector named Quinn with a monocle and white gloves, examining a printed page under a bright desk lamp"),
    ("39-figure-fact-checker", "a precise French female scientist named Celeste with a lab coat, verifying chart data against a reference notebook with colored sticky tabs"),
    ("40-code-caption-agent", "a Black male musician named Felix with headphones, annotating code blocks with descriptive captions using a glowing stylus"),
    ("41-lab-designer", "a creative white female scientist named Wren with safety goggles pushed up, designing a hands-on lab setup with beakers, circuits, and a laptop"),
]

BASE_STYLE = "Digital art avatar portrait, Kurzgesagt-inspired minimal cartoon style, clean vector lines, vibrant flat colors, circular composition, gradient background, friendly and professional, no text"

POLL_INTERVAL = 15  # seconds


def load_config():
    config_path = Path.home() / ".gemini-imagegen.json"
    if not config_path.exists():
        print("ERROR: ~/.gemini-imagegen.json not found", file=sys.stderr)
        sys.exit(1)
    return json.loads(config_path.read_text())


def build_batch_requests(agents, force=False):
    """Build inline batch requests, skipping agents that already have avatars."""
    from google.genai import types
    requests = []
    indices = []  # track which agent index maps to which request

    for i, (agent_file, description) in enumerate(agents):
        output = OUTPUT_DIR / f"{agent_file}.png"
        if output.exists() and not force:
            print(f"  SKIP (exists): {agent_file}.png")
            continue

        prompt = f"Portrait avatar of a friendly AI agent character: {description}. {BASE_STYLE}"
        requests.append(types.InlinedRequest(
            contents=[types.Content(parts=[types.Part(text=prompt)], role="user")],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(aspect_ratio="1:1", image_size="1K"),
            ),
        ))
        indices.append(i)

    return requests, indices


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate 42 agent avatars via Gemini Batch API (50% cost)")
    parser.add_argument("--force", action="store_true", help="Regenerate even if file exists")
    parser.add_argument("--sync", action="store_true", help="Use synchronous API (full price, immediate)")
    parser.add_argument("--poll", type=int, default=POLL_INTERVAL, help="Batch poll interval in seconds")
    args = parser.parse_args()

    config = load_config()
    from google import genai
    client = genai.Client(api_key=config["api_key"])
    model = config.get("default_model", "gemini-3.1-flash-image-preview")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.sync:
        run_sync(client, model, args.force)
    else:
        run_batch(client, model, args.force, args.poll)


def run_batch(client, model, force, poll_interval):
    """Submit all avatars as a single batch job at 50% cost."""
    requests, indices = build_batch_requests(AGENTS, force)

    if not requests:
        print("All avatars already exist. Use --force to regenerate.")
        return

    print(f"Submitting batch of {len(requests)} avatar requests to {model}...")
    print("  (Batch API: 50% cost, async processing)")

    batch_job = client.batches.create(
        model=model,
        src=requests,
        config={"display_name": f"avatars-batch-{int(time.time())}"},
    )

    job_name = batch_job.name
    print(f"  Job: {job_name}")
    print(f"  Polling every {poll_interval}s...")

    while True:
        batch_job = client.batches.get(name=job_name)
        state = batch_job.state.name if hasattr(batch_job.state, "name") else str(batch_job.state)
        if state in ("JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED"):
            break
        print(f"  State: {state}")
        time.sleep(poll_interval)

    if state != "JOB_STATE_SUCCEEDED":
        print(f"Batch job {state}.")
        return

    print("Batch complete. Saving avatars...")
    saved = 0
    failed = 0

    for resp_idx, resp_wrapper in enumerate(batch_job.dest.inlined_responses):
        if resp_idx >= len(indices):
            break
        agent_idx = indices[resp_idx]
        agent_file = AGENTS[agent_idx][0]
        output_path = OUTPUT_DIR / f"{agent_file}.png"

        response = resp_wrapper.response
        if not response or not response.candidates:
            print(f"  FAIL: {agent_file}.png (no image returned)")
            failed += 1
            continue

        image_saved = False
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if part.inline_data and part.inline_data.data:
                    img_data = part.inline_data.data
                    if isinstance(img_data, str):
                        img_data = base64.b64decode(img_data)
                    output_path.write_bytes(img_data)
                    print(f"  OK: {agent_file}.png")
                    saved += 1
                    image_saved = True
                    break
            if image_saved:
                break

        if not image_saved:
            print(f"  FAIL: {agent_file}.png (no image data)")
            failed += 1

    print(f"\nDone: {saved} saved, {failed} failed out of {len(requests)} requested")


def run_sync(client, model, force):
    """Fallback: synchronous generation (full price, immediate results)."""
    from google.genai import types

    success = 0
    fail = 0

    for i, (agent_file, description) in enumerate(AGENTS):
        output = OUTPUT_DIR / f"{agent_file}.png"
        if output.exists() and not force:
            print(f"  SKIP (exists): {agent_file}.png")
            continue

        prompt = f"Portrait avatar of a friendly AI agent character: {description}. {BASE_STYLE}"
        print(f"[{i+1}/{len(AGENTS)}] Generating {agent_file}...")

        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(aspect_ratio="1:1", image_size="1K"),
                ),
            )
            for part in response.parts:
                if part.inline_data is not None:
                    part.as_image().save(str(output))
                    print(f"  OK: {agent_file}.png")
                    success += 1
                    break
            else:
                print(f"  FAIL: {agent_file}.png (no image)")
                fail += 1
        except Exception as e:
            print(f"  FAIL: {agent_file}.png: {e}")
            fail += 1

        time.sleep(2)

    print(f"\nDone: {success} succeeded, {fail} failed")


if __name__ == "__main__":
    main()
