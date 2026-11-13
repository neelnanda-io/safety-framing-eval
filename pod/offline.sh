#!/bin/bash
# Make the internet unreachable by name for every command on this rented machine, except the model API the harness
# itself needs. Run as root AFTER pod/setup.sh (which downloads packages).
#
# Names are looked up through /etc/resolv.conf. With no name server listed there, `pip download`, `git fetch` and the
# like fail with "Temporary failure in name resolution", exactly as on a machine that is offline, and nothing unusual
# shows in the agent's environment. The harness reaches openrouter.ai through fixed addresses in /etc/hosts.
# Undo with:  cp /root/resolv.conf.bak /etc/resolv.conf
set -euo pipefail
[ -f /root/resolv.conf.bak ] || cp /etc/resolv.conf /root/resolv.conf.bak
IPS=$(getent ahostsv4 openrouter.ai | awk '{print $1}' | sort -u)
[ -n "$IPS" ] || { echo "could not look up openrouter.ai"; exit 1; }
grep -v ' openrouter.ai$' /etc/hosts > /root/hosts.new || true
for ip in $IPS; do echo "$ip openrouter.ai" >> /root/hosts.new; done
cat /root/hosts.new > /etc/hosts
echo "# no name servers configured" > /etc/resolv.conf
if su akim -s /bin/sh -c 'getent hosts pypi.org' >/dev/null 2>&1; then echo "FAIL: pypi.org still resolves for akim"; exit 1; fi
echo "ok: pypi.org does not resolve for akim"
su akim -s /bin/sh -c "cd /tmp && timeout 60 $(cat /root/sfe/pod/base_python.txt) -m pip download --no-deps six 2>&1 | tail -n 2" || true
/opt/harness/bin/python -c "import urllib.request; print('ok: model API reachable, HTTP', urllib.request.urlopen('https://openrouter.ai/api/v1/models', timeout=20).status)"
echo OFFLINE_DONE
