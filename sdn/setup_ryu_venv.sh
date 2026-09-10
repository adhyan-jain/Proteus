#!/usr/bin/env bash
# Sets up a dedicated Python 3.8 virtualenv for Ryu 4.34 (the SDN controller framework
# used in Stage 6/7 of the paper-grade scale-up), and patches two real compatibility gaps
# between Ryu and modern package versions. Run from the repo root:
#   bash sdn/setup_ryu_venv.sh
#
# Why a separate venv: Ryu has not been updated since ~2019 and does not run on the
# system's Python (3.14) or the main ML pipeline's venv (Python 3.12) -- its setup hooks
# and console scripts depend on packaging/stdlib internals removed in modern Python and
# modern setuptools/eventlet/oslo.config releases. This script pins the specific working
# combination found by trial: Python 3.8, setuptools<58 (pre-removal of the easy_install
# internals Ryu's install hook imports), --no-build-isolation (so the build step actually
# sees that pinned old setuptools instead of a fresh isolated one), eventlet==0.25.2 (0.31+
# removed the ALREADY_HANDLED constant Ryu's WSGI layer imports; even below that, eventlet's
# own dnspython dependency isn't tightly pinned so it must be pinned explicitly too, else a
# too-new dnspython breaks eventlet's greendns support module on import), and a small
# oslo.config compatibility shim (modern oslo-config only ships the `oslo_config` module,
# not the legacy dotted `oslo.config` namespace package several Ryu modules still import
# from).
set -euo pipefail
cd "$(dirname "$0")/.."

uv venv --python 3.8 .venv-ryu
uv pip install --python .venv-ryu/bin/python "setuptools<58" wheel
uv pip install --python .venv-ryu/bin/python --no-build-isolation "ryu==4.34"
uv pip install --python .venv-ryu/bin/python --no-build-isolation "eventlet==0.25.2" "dnspython==1.16.0"

SITE="$(.venv-ryu/bin/python -c 'import site; print(site.getsitepackages()[0])')"
mkdir -p "$SITE/oslo/config"
cat > "$SITE/oslo/__init__.py" << 'EOF'
__path__ = __import__('pkgutil').extend_path(__path__, __name__)
EOF
cat > "$SITE/oslo/config/__init__.py" << 'EOF'
import sys
from oslo_config import cfg, types, generator  # noqa
sys.modules[__name__ + '.cfg'] = cfg
sys.modules[__name__ + '.types'] = types
sys.modules[__name__ + '.generator'] = generator
EOF

echo "Verifying..."
.venv-ryu/bin/ryu-manager --version

echo
echo "Ryu venv ready. Run a controller app with:"
echo "  .venv-ryu/bin/ryu-manager <app_module>"
