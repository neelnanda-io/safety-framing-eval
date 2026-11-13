#!/bin/bash
# One-time setup of the rented Linux machine. Run as root from /root/sfe:  bash pod/setup.sh
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
id akim >/dev/null 2>&1 || useradd -m -s /bin/bash akim          # the unprivileged user every agent command runs as
# a pool of unprivileged users, one per episode running at the same time (SFE_SANDBOX_USERS); added 13 Nov 2026
for u in $(cat pod/users.txt 2>/dev/null); do id "$u" >/dev/null 2>&1 || useradd -m -s /bin/bash "$u"; done
mkdir -p /var/lock
chmod 700 /root /root/sfe

# Python 3.13 in a neutral, world-readable place (no home-folder path in tracebacks)
export UV_PYTHON_INSTALL_DIR=/opt/python
uv python install 3.13
PY=$(ls -d /opt/python/cpython-3.13*/bin/python3.13 | head -1)
echo "$PY" > pod/base_python.txt
"$PY" -V

# the harness's own environment
uv venv --quiet --python "$PY" --allow-existing /opt/harness
uv pip install --quiet --python /opt/harness/bin/python openai python-dotenv

# one environment per repository, with the exact package versions used on the laptop (CPU build of torch)
mkdir -p /var/tmp/venvs
REPOS="${*:-rsl_rl valor prompto synthetic-data-kit NeuroX dictionary_learning control-arena}"   # optional arguments: only these repositories
for n in $REPOS; do
  uv venv --quiet --python "$PY" --allow-existing /var/tmp/venvs/$n
  sed -E 's/^torch==([0-9.]+)$/torch==\1+cpu/' pod/pins/$n.txt > /root/pins_$n.txt
  uv pip install --quiet --python /var/tmp/venvs/$n/bin/python -r /root/pins_$n.txt \
      --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match
  echo "$n: $(/var/tmp/venvs/$n/bin/python -c 'import sys; print(sys.version.split()[0])') $(uv pip freeze --python /var/tmp/venvs/$n/bin/python | wc -l) packages"
done
# markers so the harness accepts these environments as built (same check as sfe.real.ensure_venv)
/opt/harness/bin/python - <<'PY'
import json
from pathlib import Path
for t in [*Path('real_tasks').glob('*/task.json'), *Path('real_tasks_new').glob('*/task.json')]:
    d = json.loads(t.read_text())
    if (Path('/var/tmp/venvs') / d['name']).exists():
        (Path('/var/tmp/venvs') / d['name'] / '.ready').write_text(json.dumps(sorted(d.get('deps', []))))
PY
chmod -R a+rX /opt/python /opt/harness /var/tmp/venvs
git config --system --add safe.directory '*' || true     # the harness (root) reads repositories owned by akim
mkdir -p logs
echo SETUP_DONE
