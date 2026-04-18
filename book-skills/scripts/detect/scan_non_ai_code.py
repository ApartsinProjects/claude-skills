"""Scan all section HTML files for code fragments that don't involve AI/ML/LLM functionality."""

import re
import os
from pathlib import Path

ROOT = Path(r"E:\Projects\LLMCourse")

# AI/ML indicators - libraries, keywords, patterns
AI_INDICATORS = [
    # Libraries
    r'\bopenai\b', r'\banthropic\b', r'\blangchain\b', r'\bllamaindex\b',
    r'\btransformers\b', r'\btorch\b', r'\bpytorch\b', r'\btensorflow\b',
    r'\bnumpy\b', r'\bscipy\b', r'\bscikit[-_]learn\b', r'\bsklearn\b',
    r'\btiktoken\b', r'\bspacy\b', r'\bnltk\b', r'\bhuggingface\b',
    r'\bsentence.transformers\b', r'\bfaiss\b', r'\bchroma\b', r'\bpinecone\b',
    r'\bweaviate\b', r'\bqdrant\b', r'\bmilvus\b', r'\blangsmith\b',
    r'\bmlflow\b', r'\bwandb\b', r'\bweights\s*&\s*biases\b',
    r'\bpeft\b', r'\btrl\b', r'\blora\b', r'\bqlora\b', r'\baxolotl\b',
    r'\bvllm\b', r'\btgi\b', r'\bollama\b', r'\bllama\.cpp\b',
    r'\bcrew.?ai\b', r'\bautogen\b', r'\blanggraph\b', r'\bsemantic.kernel\b',
    r'\bgpt[-_]?\d\b', r'\bclaude\b', r'\bgemini\b', r'\bllama\b', r'\bmistral\b',
    r'\bragas\b', r'\bdeepeval\b', r'\blm[-_]eval\b',
    r'\bgradio\b', r'\bstreamlit\b', r'\bchainlit\b',
    r'\bpandas\b',  # often used for data processing in ML
    r'\bmatplotlib\b', r'\bseaborn\b',  # visualization of ML results
    r'\bdatasets\b',  # HuggingFace datasets

    # AI/ML concepts in code
    r'\bembedding[s]?\b', r'\btokeniz\w+\b', r'\btoken[s]?\b',
    r'\bprompt\b', r'\bcompletion[s]?\b', r'\bchat\.completions?\b',
    r'\bmodel\b', r'\bllm\b', r'\bagent\b', r'\btool_call\b',
    r'\bvector.?(store|db|database|search|index)\b',
    r'\brag\b', r'\bretrieval\b', r'\bchunk\b',
    r'\bfine.?tun\w+\b', r'\brlhf\b', r'\bdpo\b', r'\bppo\b',
    r'\bloss\b', r'\bgradient\b', r'\boptimizer\b', r'\bbackprop\b',
    r'\battention\b', r'\btransformer\b', r'\bself[-_]attention\b',
    r'\bsoftmax\b', r'\bcross.?entropy\b', r'\bperplexity\b',
    r'\bbeam.?search\b', r'\bgreedy\b', r'\btemperature\b',
    r'\btop.?[pk]\b', r'\bsampling\b',
    r'\bnerual\b', r'\bneural\b', r'\bnn\.\b', r'\bnn\.Module\b',
    r'\bepoch\b', r'\bbatch\b', r'\btraining\b',
    r'\binference\b', r'\bpredict\w*\b', r'\bgenerat\w+\b',
    r'\bsentiment\b', r'\bclassif\w+\b', r'\bner\b', r'\bnamed.entity\b',
    r'\bsummariz\w+\b', r'\btranslat\w+\b',
    r'\bcosine.?similarity\b', r'\bsemantic.?search\b',
    r'\bfunction.?call\w*\b', r'\btool.?use\b',
    r'\bsystem.?message\b', r'\buser.?message\b', r'\bassistant.?message\b',
    r'\brole\b.*\b(system|user|assistant)\b',
    r'\bapi.?key\b', r'\bOPENAI\b', r'\bANTHROPIC\b',
    r'\bchat\b', r'\bconvers\w+\b',
    r'\bmemory\b',  # agent memory
    r'\bchain\b',  # langchain concept
    r'\bloader\b',  # document loader
    r'\bsplitter\b',  # text splitter
    r'\bparser\b',  # output parser
    r'\bguardrail\b', r'\bsafety\b', r'\bfilter\b',
    r'\beval\w*\b',  # evaluation
    r'\bmetric\b', r'\bscore\b', r'\baccuracy\b', r'\bf1\b', r'\bbleu\b', r'\brouge\b',
    r'\blatency\b', r'\bthroughput\b',
    r'\bdeploy\b', r'\bserving\b', r'\bendpoint\b',
    r'\bcontainer\b', r'\bdocker\b', r'\bkubernetes\b',
    r'\bapi\b', r'\brest\b', r'\bfastapi\b', r'\bflask\b',
    r'\bwebsocket\b', r'\bstream\b',
    r'\bguard\b', r'\bvalidat\w+\b',
    r'\bpydantic\b',
    r'\basync\b', r'\bawait\b',
    r'\bprocess\b', r'\bpipeline\b',
    r'\bcallback\b', r'\bhook\b',
    r'\bregist\w+\b', r'\bdispatch\b',
    r'\blog\b', r'\bmonitor\b', r'\btrace\b', r'\bobserv\b',
]

# More restrictive: things that are clearly NOT AI
NON_AI_PATTERNS = [
    r'@dataclass\b.*\n(?:.*\n)*?.*(?:name|title|description|status|priority|date|email|phone|address)',
    r'class\s+\w+.*:\n\s+""".*(?:project|task|employee|customer|order|invoice|product)',
]

def extract_code_blocks_with_captions(html_content, filepath):
    """Extract code blocks that are immediately followed by a Code Fragment caption."""
    results = []

    # Find all code-caption divs
    caption_pattern = r'<div class="code-caption"><strong>(Code Fragment [\d\w.]+):</strong>\s*(.*?)</div>'

    for cap_match in re.finditer(caption_pattern, html_content, re.DOTALL):
        fragment_id = cap_match.group(1)
        caption_text = cap_match.group(2).strip()
        cap_start = cap_match.start()

        # Look backwards for the nearest <pre><code block before this caption
        # Search in the region before the caption
        before_text = html_content[:cap_start]

        # Find the last <pre><code...>...</code></pre> before the caption
        code_pattern = r'<pre><code[^>]*>(.*?)</code></pre>'
        code_matches = list(re.finditer(code_pattern, before_text, re.DOTALL))

        if code_matches:
            last_code = code_matches[-1]
            code_content = last_code.group(1)
            # Decode HTML entities
            code_content = code_content.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&').replace('&#39;', "'").replace('&quot;', '"')

            results.append({
                'fragment_id': fragment_id,
                'caption': caption_text,
                'code': code_content,
                'file': str(filepath),
            })

    return results


def is_ai_related(code, caption):
    """Check if code or caption contains AI/ML indicators."""
    combined = (code + " " + caption).lower()

    for pattern in AI_INDICATORS:
        if re.search(pattern, combined, re.IGNORECASE):
            return True
    return False


def describe_code(code):
    """Generate a brief description of what the code does."""
    lines = [l.strip() for l in code.strip().split('\n') if l.strip() and not l.strip().startswith('#')]

    # Check for dataclass
    if '@dataclass' in code:
        classes = re.findall(r'class\s+(\w+)', code)
        return f"Defines dataclass(es): {', '.join(classes)}"

    # Check for class definitions
    classes = re.findall(r'class\s+(\w+)', code)
    if classes:
        return f"Defines class(es): {', '.join(classes)}"

    # Check for function definitions
    funcs = re.findall(r'def\s+(\w+)', code)
    if funcs:
        return f"Defines function(s): {', '.join(funcs)}"

    # Check for print statements
    if 'print(' in code:
        return "Prints output/values"

    # Check for enum
    if 'Enum' in code:
        return "Defines an Enum type"

    # Fallback
    if len(lines) > 0:
        return f"Code starting with: {lines[0][:80]}"
    return "Empty or minimal code"


def main():
    flagged = []
    total = 0

    # Find all section HTML files
    for html_file in sorted(ROOT.rglob('section-*.html')):
        # Skip agent files
        if 'agents' in str(html_file):
            continue

        content = html_file.read_text(encoding='utf-8', errors='replace')
        blocks = extract_code_blocks_with_captions(content, html_file)

        for block in blocks:
            total += 1
            if not is_ai_related(block['code'], block['caption']):
                rel_path = os.path.relpath(block['file'], ROOT)
                flagged.append({
                    'file': rel_path,
                    'fragment_id': block['fragment_id'],
                    'code_preview': block['code'][:500],
                    'caption': block['caption'],
                })

    print(f"Total code fragments scanned: {total}")
    print(f"Non-AI code fragments found: {len(flagged)}")
    print("=" * 80)

    for item in flagged:
        print(f"\nFile: {item['file']}")
        print(f"Fragment: {item['fragment_id']}")
        print(f"Caption: {item['caption'][:120]}")
        print(f"Code preview:")
        print(item['code_preview'])
        print("-" * 60)


if __name__ == '__main__':
    main()
