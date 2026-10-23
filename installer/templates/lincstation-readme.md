# Your LincStation E1

This NAS runs **Debian 13** and **OpenMediaVault 8**. Its stock Android firmware was replaced by the LincStation E1 migration toolkit:
https://github.com/bourbonicfisky/lincstation-e1-debian

Open this guide any time with `lincstation-help`. It's also at `~/LINCSTATION-README.md` and `/usr/local/share/doc/lincstation/README.md`.

## Everyday use

- **OpenMediaVault (storage, shares, users, updates):** http://@NAS_IP@/ from any browser on your network. Log in as `admin`. The password is in `LOGIN.txt` in the private work folder on the computer you installed from.
- **SSH:** `ssh @USER@@@NAS_IP@` with the key from the work folder. `@USER@` can use `sudo`. Root logs in with the key only.
- **Desktop (if installed):** log in on the HDMI screen as `@USER@`, then run `startx`. Log out to free the memory again.
- **Log in to the desktop automatically at boot:** `sudo lincstation-autologin on @USER@` (or `off`), like a Raspberry Pi. Anyone at the HDMI screen then gets your desktop without a password; `sudo` still asks for one.
- **Remote desktop (if installed):** start the desktop first, then run `connect-vnc.sh` from the toolkit on your computer and open `vnc://127.0.0.1:15900`.

## Fan

The fan follows the CPU temperature. It has three profiles:

| Profile | Fan |
| --- | --- |
| `quiet` | Quietest; the drives run a few degrees warmer |
| `balanced` | Default; quiet at idle, speeds up sooner under load |
| `performance` | Coolest drives; about 2,250 RPM even at idle |

```sh
lincstation-fan status                 # profile, temperatures and fan speed (sudo adds drive temperatures)
sudo lincstation-fan performance       # or quiet / balanced; saved for future boots
```

For your own curve, edit `/etc/default/lincstation-fan`. Set `FAN_PROFILE=custom` and the three temperatures, then run `sudo systemctl restart lincstation-fan`. Keep the drives under about 45 °C.

## Wi-Fi and Bluetooth

The built-in Realtek RTL8822CS works on 2.4 and 5 GHz Wi-Fi and Bluetooth.

- `iw dev wlan0 scan | grep SSID` lists Wi-Fi networks.
- To join one, use OMV's *Network → Interfaces* page.
- `bluetoothctl` handles Bluetooth: `power on`, `scan on`, `pair`, `connect`.

Joining Wi-Fi networks and pairing Bluetooth devices haven't been tested on the E1 yet.

## Video playback

VLC and mpv decode video on the CPU. For hardware decoding of H.264 and MPEG-2 (up to 1080p) and VP8, install GStreamer and a GStreamer player, then open videos in Parole:

```sh
sudo apt-get install --no-install-recommends gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav parole
```

HEVC/H.265, VP9 and 4K H.264 always decode on the CPU.

## Updates

Install updates as usual, with `sudo apt update && sudo apt upgrade` or OMV's *Update Management* page.

The E1's bootloader doesn't read `/boot`. After a kernel update, a hook rebuilds the boot image and writes it to boot slot A, keeping recovery slot B as a fallback. Reboot once afterwards to start the new kernel.

**Never write to the eMMC's boot, bootloader or partition-table areas by hand.**

## If something goes wrong

- **The NAS doesn't come back after a restart:** unplug the power cable for 10 seconds, plug it back in, and switch it on. The front button doesn't fully cut power.
- **A new kernel won't boot:** the bootloader falls back to the RAM recovery system in slot B on its own. Recovery answers SSH as `root` on port 2223 at @NAS_IP@. It mounts no disks.
- **To start recovery on purpose:** run `sudo lincstation-update-kernel --recovery`, then `sudo systemctl reboot`.
- **Logs:** `journalctl -b` for this boot, and `/var/log/lincstation-early-boot.log` for early startup.

## Useful commands

| Command | What it does |
| --- | --- |
| `lincstation-help` | Show this guide |
| `lincstation-fan status` | Fan profile, temperatures, fan speed |
| `sudo lincstation-fan quiet\|balanced\|performance` | Change the fan profile |
| `sudo lincstation-autologin on @USER@\|off` | Boot straight into the desktop, or not |
| `sudo smartctl -a /dev/sda` | Drive health (also `/dev/sdb`) |
| `sudo lincstation-update-kernel --recovery` | Boot RAM recovery next time |
| `systemctl --failed` | Show any failed services |
