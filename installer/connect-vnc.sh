#!/bin/sh
# Run on your client computer. A desktop must already be running on the NAS.
set -eu
host=${1:?Usage: ./connect-vnc.sh USER@NAS_IP SSH_PRIVATE_KEY [KNOWN_HOSTS_FILE]}
key=${2:?Supply your SSH private key path}
known=${3:-}
case "$host" in -*|*[!a-zA-Z0-9@._:-]*) echo 'Invalid SSH destination'; exit 1;; esac
port=${VNC_LOCAL_PORT:-15900}
case "$port" in ''|*[!0-9]*) echo 'Invalid local port'; exit 1;; esac
if [ -n "$known" ]; then
  set -- -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known"
else
  set -- -o StrictHostKeyChecking=ask
fi
printf 'Leave this terminal open. Connect your VNC viewer to 127.0.0.1:%s.\n' "$port"
ssh "$@" -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -N \
  -L "127.0.0.1:$port:127.0.0.1:5900" -i "$key" "$host"
