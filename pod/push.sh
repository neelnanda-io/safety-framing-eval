#!/bin/sh
# Copy the harness, the task definitions and the named repository clones to the rented machine in pod/host.txt, and give
# it the OpenRouter key (that one line and nothing else from the laptop's .env).   Usage: pod/push.sh rsl_rl NeuroX ...
# A name containing a slash is a path under real_repos/ (e.g. new/control-arena, the new-repository clones of 13 Nov 2026).
cd "$(dirname "$0")/.." || exit 1
read -r POD IP PORT < "${SFE_POD_HOST:-pod/host.txt}"
RS="ssh -i ${SFE_POD_SSH_KEY:-$HOME/.ssh/id_ed25519} -o StrictHostKeyChecking=accept-new -o LogLevel=ERROR -o ConnectTimeout=20 -p $PORT"
pod/ssh.sh 'mkdir -p /root/sfe/real_repos/candidates /root/sfe/real_repos/new /root/sfe/logs && chmod 700 /root /root/sfe' || exit 2
rsync -az --exclude __pycache__ -e "$RS" sfe real_tasks real_tasks_new pod root@"$IP":/root/sfe/ || exit 2
for r in "$@"; do
  case "$r" in
    */*) rsync -az -e "$RS" "real_repos/$r" root@"$IP":/root/sfe/real_repos/"$(dirname "$r")"/ || exit 2 ;;
    *)   rsync -az -e "$RS" "real_repos/candidates/$r" root@"$IP":/root/sfe/real_repos/candidates/ || exit 2 ;;
  esac
done
pod/ssh.sh 'chown -R root:root /root/sfe' || exit 2     # copies arrive owned by the laptop's user id, which git refuses to read
grep '^OPENROUTER_API_KEY=' .env | pod/ssh.sh 'umask 077; cat > /root/sfe/.env' || exit 2
pod/ssh.sh 'cd /root/sfe && echo "key lines on the machine: $(wc -l < .env)" && ls && ls real_repos/candidates'
