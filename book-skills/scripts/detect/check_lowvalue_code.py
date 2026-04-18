#!/usr/bin/env python3
"""Detect code fragments that may not add pedagogical value.

Scans all section HTML files for code blocks that:
- Only define a class/dataclass/enum with no usage
- Only print what was hardcoded in the input
- Contain no function calls to external libraries
- Are pure configuration/schema definitions

Outputs a report of suspicious fragments for human review.
"""

import re
import sys
from pathlib import Path

# Patterns that suggest a code block is low-value
DEFINITION_ONLY_PATTERNS = [
    # Dataclass/class definitions that end with just instantiation + print
    r'@dataclass.*?class\s+\w+',
    r'class\s+\w+\(BaseModel\)',
    r'class\s+\w+\(Enum\)',
    r'class\s+\w+\(TypedDict\)',
]

# Patterns that suggest the code IS doing something useful
VALUE_INDICATORS = [
    # API calls
    r'\.create\(', r'\.generate\(', r'\.invoke\(', r'\.run\(',
    r'requests\.(get|post|put|delete)\(',
    # Data processing
    r'\.fit\(', r'\.transform\(', r'\.predict\(',
    r'pd\.DataFrame', r'np\.', r'torch\.',
    r'numpy', r'scipy', r'sklearn',
    # File I/O
    r'open\(', r'\.read\(', r'\.write\(',
    r'json\.loads?\(', r'json\.dumps?\(',
    # Visualization
    r'plt\.', r'\.plot\(', r'\.show\(',
    r'matplotlib',
    # LLM/AI specific
    r'openai\.',  r'anthropic\.', r'ChatCompletion',
    r'tokenize', r'embed', r'encode\(',
    r'pipeline\(', r'AutoModel', r'from_pretrained',
    r'transformers', r'huggingface', r'langchain', r'llama',
    r'tiktoken', r'gensim', r'spacy', r'nltk',
    r'deepspeed', r'accelerate', r'bitsandbytes',
    # Algorithms/computation
    r'for\s+\w+\s+in\s+', r'while\s+',
    r'sorted\(', r'filter\(', r'map\(',
    r'\.apply\(', r'\.groupby\(',
    r'def\s+\w+\(.*\):', # Function definitions that DO something
    r'return\s+',  # Functions with return values
    r'if\s+.*:', # Control flow
    r'try:', r'except',
    # Testing/assertion
    r'assert\s+', r'\.assertEqual',
    # HTTP/web
    r'FastAPI', r'app\.(get|post|route)',
    r'streamlit', r'gradio',
    # Database
    r'cursor\.execute', r'\.query\(',
    # Subprocess/system
    r'subprocess\.', r'os\.system',
    # Shell commands
    r'pip install', r'torchrun', r'deepspeed',
    # Config display (these are intentionally showing config structure)
    r'deepspeed_config',
    # Prompt templates (showing prompt structure is valid)
    r'prompt\s*=\s*["\']', r'system.*=.*["\']',
    # Evaluation
    r'evaluate\.load', r'metric', r'rouge', r'bleu',
]

# Patterns suggesting output is just echoing input
ECHO_PATTERNS = [
    r'print\(.*\.summary\(\)\)',
    r'print\(f".*\{.*\}".*\)$',  # Simple f-string prints
    r'pprint\(',
]


def extract_code_blocks(html_content):
    """Extract code blocks and their captions from HTML."""
    # Match <pre><code>...</code></pre> blocks
    pattern = r'<pre><code[^>]*>(.*?)</code></pre>'
    blocks = []
    for match in re.finditer(pattern, html_content, re.DOTALL):
        code = match.group(1)
        # Decode HTML entities
        code = code.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
        code = code.replace('&#39;', "'").replace('&quot;', '"')

        # Find associated caption
        caption_match = re.search(
            r'<div class="code-caption"><strong>(Code Fragment [\d.]+):</strong>\s*(.*?)</div>',
            html_content[match.end():match.end()+500]
        )
        caption_id = caption_match.group(1) if caption_match else "Unknown"
        caption_text = caption_match.group(2) if caption_match else ""

        blocks.append({
            'code': code,
            'caption_id': caption_id,
            'caption_text': caption_text,
            'start': match.start(),
        })
    return blocks


def has_value_indicators(code):
    """Check if code contains patterns suggesting it does something useful."""
    # Strip HTML tags for cleaner pattern matching
    clean = re.sub(r'<[^>]+>', '', code)
    for pattern in VALUE_INDICATORS:
        if re.search(pattern, clean, re.IGNORECASE):
            return True
    return False


def is_definition_heavy(code):
    """Check if code is primarily class/schema definitions."""
    code = re.sub(r'<[^>]+>', '', code)
    lines = [l.strip() for l in code.split('\n') if l.strip() and not l.strip().startswith('#')]
    if not lines:
        return False

    def_lines = 0
    for line in lines:
        if any(kw in line for kw in ['class ', '@dataclass', 'Enum)', 'BaseModel)',
                                       ': str', ': int', ': float', ': bool', ': list',
                                       ': Optional', ': dict', '= field(',
                                       '= ""', '= 0', '= False', '= True', '= None',
                                       '"""', "'''"]):
            def_lines += 1

    return def_lines / len(lines) > 0.5


def is_echo_output(code):
    """Check if the only 'action' is printing hardcoded values."""
    code = re.sub(r'<[^>]+>', '', code)
    action_lines = []
    for line in code.split('\n'):
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('class ') or line.startswith('@'):
            continue
        if ':' in line and '=' not in line and 'print' not in line:
            continue  # Type annotation line
        if '=' in line and 'print' not in line and '(' not in line:
            continue  # Simple assignment
        if 'print' in line or 'pprint' in line:
            action_lines.append(('print', line))
        elif '(' in line:
            action_lines.append(('call', line))

    if not action_lines:
        return True

    print_count = sum(1 for t, _ in action_lines if t == 'print')
    call_count = sum(1 for t, _ in action_lines if t == 'call')

    # If all actions are just prints or simple instantiation + print
    return print_count > 0 and call_count <= 1


def analyze_code_block(block):
    """Analyze a code block and return concerns if it's low-value."""
    code = block['code']
    concerns = []

    # Skip non-Python blocks
    if any(kw in code[:50] for kw in ['$ ', 'bash', 'curl', '<!DOCTYPE', '<html']):
        return None

    # Check for value indicators first (these are likely good)
    if has_value_indicators(code):
        return None

    # Check if it's mostly definitions
    if is_definition_heavy(code):
        concerns.append("Primarily class/schema definitions")

    # Check if output is just echoing
    if is_echo_output(code):
        concerns.append("Output appears to only echo hardcoded values")

    # Very short code that just instantiates and prints
    lines = [l for l in code.split('\n') if l.strip() and not l.strip().startswith('#')]
    if len(lines) < 5 and 'print' in code:
        concerns.append("Very short block that only prints")

    if concerns:
        return concerns
    return None


def scan_file(filepath):
    """Scan a single HTML file for low-value code fragments."""
    content = filepath.read_text(encoding='utf-8', errors='replace')
    blocks = extract_code_blocks(content)
    findings = []

    for block in blocks:
        concerns = analyze_code_block(block)
        if concerns:
            findings.append({
                'file': str(filepath),
                'caption_id': block['caption_id'],
                'caption_text': block['caption_text'][:100],
                'concerns': concerns,
                'code_preview': block['code'][:200].replace('\n', '\n    '),
            })

    return findings


def main():
    book_root = Path(__file__).parent.parent.parent

    # Find all section HTML files
    section_files = sorted(book_root.glob('part-*/module-*/section-*.html'))

    print(f"Scanning {len(section_files)} section files for low-value code fragments...\n")

    all_findings = []
    for filepath in section_files:
        findings = scan_file(filepath)
        all_findings.extend(findings)

    if not all_findings:
        print("No low-value code fragments detected.")
        return

    print(f"Found {len(all_findings)} potentially low-value code fragments:\n")
    print("=" * 80)

    for i, f in enumerate(all_findings, 1):
        rel_path = Path(f['file']).relative_to(book_root)
        print(f"\n{i}. {f['caption_id']} in {rel_path}")
        if f['caption_text']:
            print(f"   Caption: {f['caption_text']}")
        print(f"   Concerns: {'; '.join(f['concerns'])}")
        print(f"   Preview:")
        for line in f['code_preview'].split('\n')[:6]:
            print(f"      {line}")
        print("-" * 80)


if __name__ == '__main__':
    main()
