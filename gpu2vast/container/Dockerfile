FROM pytorch/pytorch:2.3.0-cuda12.1-cudnn9-runtime

# System packages
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Python packages
RUN pip install --no-cache-dir \
    transformers accelerate peft trl bitsandbytes \
    sentence-transformers datasets \
    boto3 requests

# GPU2Vast container scripts
COPY entrypoint.sh r2_download.py r2_upload.py progress_reporter.py /gpu2vast/
RUN chmod +x /gpu2vast/entrypoint.sh

# Pre-download models (baked in, no runtime download)
ARG MODELS=""
RUN if [ -n "$MODELS" ]; then \
    python -c "from transformers import AutoModelForCausalLM, AutoTokenizer; \
    [AutoTokenizer.from_pretrained(m) or AutoModelForCausalLM.from_pretrained(m) for m in '$MODELS'.split(',')]"; \
    fi

WORKDIR /workspace
ENTRYPOINT ["/gpu2vast/entrypoint.sh"]
