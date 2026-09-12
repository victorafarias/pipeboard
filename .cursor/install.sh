#!/usr/bin/env bash
# Idempotent dependency setup for the Pipeboard MCP servers.
set -euo pipefail

cd "$(dirname "$0")/.."

# System packages required to create a virtualenv and build native wheels
# (grpcio, cffi, etc.). apt is a no-op when the packages are already present.
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv python3-dev build-essential

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt -e .
