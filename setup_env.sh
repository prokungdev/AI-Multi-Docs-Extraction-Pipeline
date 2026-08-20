#!/usr/bin/env bash
# Shell wrapper script to launch cross-platform Python environment setup
set -e

echo "=========================================================="
echo " AI Multi-Docs Extraction Pipeline - Environment Setup"
echo "=========================================================="
echo ""

# Execute cross-platform Python setup script
python3 setup_env.py || python setup_env.py
