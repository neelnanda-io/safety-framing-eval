#!/bin/sh
# Run a command on the rented machine named in pod/host.txt (one line: "<pod id> <ip> <ssh port>"). Usage: pod/ssh.sh 'command'
read -r POD IP PORT < "${SFE_POD_HOST:-$(dirname "$0")/host.txt}"     # SFE_POD_HOST names another machine's file
exec ssh -i ${SFE_POD_SSH_KEY:-$HOME/.ssh/id_ed25519} -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -o ServerAliveInterval=30 -o LogLevel=ERROR -p "$PORT" root@"$IP" "$@"
