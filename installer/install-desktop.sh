#!/bin/sh
# Debian 13 / OMV-compatible, on-demand LXDE desktop and everyday applications.
set -eu
user=${1:?Usage: sudo ./install-desktop.sh EXISTING_USER [--live] [--apps web,media,utilities|all|none]}
shift
live=; apps=all
while [ $# -gt 0 ]; do
    case "$1" in
        --live) live=--live ;;
        --apps) apps=${2:?--apps needs a comma-separated list}; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
    shift
done
[ "$(id -u)" = 0 ] || { echo 'Run as root'; exit 1; }
. /etc/os-release
[ "$ID" = debian ] && [ "$VERSION_ID" = 13 ] || { echo 'This installer targets Debian 13'; exit 1; }
id "$user" >/dev/null
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export DEBIAN_FRONTEND=noninteractive
# Base desktop: always installed when the desktop is selected.
packages='lxde-common openbox-lxde-session lxsession lxpanel lxappearance lxinput lxrandr lxtask lxterminal i3lock lxlock xserver-xorg-core xserver-xorg-input-libinput xinit xauth x11-utils x11-xserver-utils dbus-user-session fonts-dejavu-core adwaita-icon-theme pcmanfm libgl1-mesa-dri mesa-utils'
[ "$apps" = all ] && apps=web,media,utilities
[ "$apps" = none ] && apps=
for group in $(printf '%s' "$apps" | tr ',' ' '); do
    case "$group" in
        web) packages="$packages firefox-esr" ;;
        media) packages="$packages ffmpeg vlc mpv alsa-utils" ;;
        utilities) packages="$packages mousepad gpicview xarchiver galculator scrot zip unzip 7zip htop" ;;
        *) echo "Unknown app group: $group (choose web, media, utilities, all or none)"; exit 1 ;;
    esac
done
plan=$(mktemp); trap 'rm -f "$plan"' EXIT HUP INT TERM
apt-get update
apt-get -s --no-install-recommends install $packages > "$plan"
if grep -Eq '^Remv |^Inst (lightdm|gdm3|sddm|lxdm|slim|xdm|wdm) ' "$plan"; then
    cat "$plan"; echo 'Stopped: plan removes packages or adds an OMV-conflicting display manager.'; exit 1
fi
apt-get -y --no-install-recommends install $packages
python3 "$base/configure-desktop.py" "$user" $live
echo "Ready: log in locally as $user and run startx. No passwords were changed."
echo
echo "Hardware video playback: VLC and mpv decode on the CPU. For hardware H.264/MPEG-2 (up to 1080p) and VP8 decoding, run:"
echo "  sudo apt-get install --no-install-recommends gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav parole"
echo "and play videos in Parole or another GStreamer player. See ~/Desktop-README.txt."
