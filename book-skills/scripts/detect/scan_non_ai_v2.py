"""Scan all section HTML files for code fragments that don't involve AI/ML/LLM functionality.
Version 2: More targeted, less prone to false positives."""

import re
import os
from pathlib import Path

ROOT = Path(r"E:\Projects\LLMCourse")

# Strong AI indicators - things that definitively mark code as AI-related
STRONG_AI_INDICATORS = [
    # AI/ML Libraries
    r'\bopenai\b', r'\banthropic\b', r'\blangchain\b', r'\bllamaindex\b',
    r'\btransformers\b', r'\bAutoModel\b', r'\bAutoTokenizer\b',
    r'\btorch\b', r'\bpytorch\b', r'\btensorflow\b', r'\btf\.\b',
    r'\bnumpy\s+as\s+np\b', r'\bimport\s+numpy\b',
    r'\bscikit.learn\b', r'\bsklearn\b',
    r'\btiktoken\b', r'\bspacy\b', r'\bnltk\b',
    r'\bsentence.transformers\b', r'\bfaiss\b', r'\bchroma\b', r'\bpinecone\b',
    r'\bweaviate\b', r'\bqdrant\b', r'\bmilvus\b',
    r'\bmlflow\b', r'\bwandb\b',
    r'\bpeft\b', r'\btrl\b', r'\bLoraConfig\b',
    r'\bvllm\b', r'\bollama\b',
    r'\bcrew.?ai\b', r'\bautogen\b', r'\blanggraph\b', r'\bStateGraph\b',
    r'\bragas\b', r'\bdeepeval\b',
    r'\bgradio\b', r'\bstreamlit\b', r'\bchainlit\b',
    r'\bdatasets\b',  # HuggingFace
    r'\bmatplotlib\b', r'\bseaborn\b',
    r'\bpandas\b',

    # API calls
    r'chat\.completions\.create', r'client\.chat\b', r'client\.messages\b',
    r'\.generate\(', r'\.predict\(', r'\.encode\(',
    r'openai\.', r'anthropic\.', r'Anthropic\(',

    # Model/ML concepts in code
    r'\bembedding', r'\btokeniz\w+', r'\btoken_count\b', r'\bnum_tokens\b',
    r'\bprompt\b', r'\bsystem_prompt\b', r'\bsystem.message\b',
    r'\bcompletion', r'\bllm\b', r'\bLLM\b',
    r'\bvector.?(store|db|database|search|index)\b',
    r'\bfine.?tun', r'\brlhf\b', r'\bdpo\b',
    r'\bloss\b', r'\bgradient\b', r'\boptimizer\b', r'\bbackward\(\)',
    r'\battention\b', r'\bself.attention\b', r'\bmultihead\b',
    r'\bsoftmax\b', r'\bcross.?entropy\b', r'\bperplexity\b',
    r'\bbeam.?search\b', r'\btemperature\b', r'\btop_p\b', r'\btop_k\b',
    r'\bnn\.Module\b', r'\bnn\.Linear\b', r'\bnn\.\b',
    r'\bepoch\b', r'\bbatch_size\b',
    r'\binference\b',
    r'\bsentiment\b', r'\bclassif\w+\b', r'\bnamed.entity\b',
    r'\bcosine.similarity\b', r'\bsemantic.search\b',
    r'\bfunction.?call\b', r'\btool_call\b', r'\btool.?use\b',
    r'\brole.*(?:system|user|assistant)\b',
    r'\bapi.?key\b', r'\bOPENAI_API_KEY\b', r'\bANTHROPIC_API_KEY\b',
    r'\bmodel_name\b', r'\bmodel_id\b',
    r'\bguardrail\b', r'\bsafety_filter\b',
    r'\bbleu\b', r'\brouge\b', r'\bf1.?score\b',
    r'\bthroughput\b', r'\btokens?.per.?second\b',
    r'\bserving\b', r'\bendpoint\b',
    r'\bdocker\b', r'\bkubernetes\b',
    r'\bfastapi\b', r'\bflask\b',
    r'\bpydantic\b',
    r'\bpipeline\b',
    r'\bnvidia.smi\b', r'\bcuda\b', r'\bgpu\b',
    r'\bchunk\b', r'\bsplitter\b', r'\bloader\b',
    r'\bRetrieval\b', r'\bRAG\b',

    # AI-related shell commands
    r'\bpip install\b', r'\bconda install\b',
    r'\bnvidia-smi\b', r'\bjupyter\b',
    r'\bnerfstudio\b', r'\bns-viewer\b', r'\bns-export\b',

    # Prompt-related
    r'""".*(?:you are|your role|respond|answer|classify|summarize|analyze)\b',
    r"'''.*(?:you are|your role|respond|answer|classify|summarize|analyze)\b",

    # AI product development
    r'\bprompt.?version\b', r'\bgolden.?test\b', r'\beval\b',
    r'\bthreat.?model\b', r'\bhallucin\w+\b',
    r'\bconfidence\b', r'\bthreshold\b',
    r'\bmodel.?tier\b', r'\bfallback\b',
    r'\bcost.?per.?token\b', r'\btoken.?budget\b',
    r'\blatency\b', r'\bp50\b', r'\bp99\b',
    r'\bprompt.?inject\b', r'\bjailbreak\b',
    r'\bai.?generated\b', r'AI_GENERATED',
    r'\bIEB\b', r'\bieb\b',
    r'\bscorer\b', r'\bscore\b',
    r'\broute\b.*\bmodel\b',
    r'\bLLMRequest\b', r'\bLLMResponse\b',
    r'\bprovider\b',
]

def extract_code_blocks_with_captions(html_content, filepath):
    """Extract code blocks that are immediately followed by a Code Fragment caption."""
    results = []
    caption_pattern = r'<div class="code-caption"><strong>(Code Fragment [\d\w.]+):</strong>\s*(.*?)</div>'

    for cap_match in re.finditer(caption_pattern, html_content, re.DOTALL):
        fragment_id = cap_match.group(1)
        caption_text = cap_match.group(2).strip()
        cap_start = cap_match.start()
        before_text = html_content[:cap_start]
        code_pattern = r'<pre><code[^>]*>(.*?)</code></pre>'
        code_matches = list(re.finditer(code_pattern, before_text, re.DOTALL))

        if code_matches:
            last_code = code_matches[-1]
            code_content = last_code.group(1)
            code_content = code_content.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&').replace('&#39;', "'").replace('&quot;', '"')
            results.append({
                'fragment_id': fragment_id,
                'caption': caption_text,
                'code': code_content,
                'file': str(filepath),
            })

    return results


def is_ai_related(code, caption):
    """Check if code or caption contains strong AI/ML indicators."""
    combined = (code + " " + caption)
    for pattern in STRONG_AI_INDICATORS:
        if re.search(pattern, combined, re.IGNORECASE):
            return True
    return False


def main():
    flagged = []
    total = 0

    for html_file in sorted(ROOT.rglob('section-*.html')):
        if 'agents' in str(html_file) or '_archive' in str(html_file):
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
                    'code': block['code'],
                    'caption': block['caption'],
                })

    print(f"Total code fragments scanned: {total}")
    print(f"Potentially non-AI code fragments: {len(flagged)}")
    print("=" * 80)

    for item in flagged:
        print(f"\nFile: {item['file']}")
        print(f"Fragment: {item['fragment_id']}")
        print(f"Caption: {item['caption'][:200]}")
        print(f"Code ({len(item['code'])} chars):")
        print(item['code'][:800])
        print("-" * 60)


if __name__ == '__main__':
    main()
