#!/bin/sh
# Run inside the pinned Linux Python 3.13 image.  Mount PIP_CACHE_DIR from the
# host so an interrupted resolver run can resume its downloads.
set -eu

: "${PIP_CACHE_DIR:=/root/.cache/pip}"
export PIP_CACHE_DIR

PYPI_INDEX="https://pypi.org/simple"
PYTORCH_CPU_INDEX="https://download.pytorch.org/whl/cpu"

python -m pip install --upgrade pip pip-tools
pip-compile --generate-hashes --resolver=backtracking \
    --index-url "$PYPI_INDEX" \
    --find-links "$PYTORCH_CPU_INDEX" \
    --output-file constraints-py313.txt requirements.txt
pip install --cache-dir "$PIP_CACHE_DIR" \
    --index-url "$PYPI_INDEX" \
    --find-links "$PYTORCH_CPU_INDEX" \
    -c constraints-py313.txt -r requirements.txt
python -c "import torch, sentence_transformers, onnxruntime, chromadb, langgraph, fitz, rapidocr_onnxruntime, pymysql; print('imports-ok', torch.__version__)"
if pip list --format=freeze | grep -qi '^nvidia-'; then
    echo "NVIDIA distributions are not allowed in the CPU runtime lock" >&2
    exit 1
fi

# This marker is deliberately written last: an interrupted resolve/install/import
# run leaves a lock that CI will refuse to present as a verified Linux lock.
printf '%s\n' \
    '# Generated from a clean Linux Python 3.13 resolution after install, import smoke test, and NVIDIA-package rejection.' \
    >> constraints-py313.txt
