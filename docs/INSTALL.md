# Installation guide

This is an **experimental, staged migration toolkit**, based on a successful migration of one LincStation E1 (Techvision TVD8322R, RK3568, 4 GB RAM, 64 GB eMMC). It covers stock root access, verified backups, native ARM64 image building, RAM recovery tests, eMMC installation, OMV, a lightweight desktop/apps, VNC and kernel maintenance.

The manual migration and the installed system have been boot-tested on that E1. The reusable image builder has been tested on a Debian 13 ARM64 helper with fresh keys and a fictitious device identity. The newly generalized stock-root/flash orchestration has **not** been run end to end on a second stock E1. Do not describe this release as a generally validated installer.

## Requirements and supported starting state

- A **helper computer**, either macOS or Debian 13 Linux (ARM64 or x86-64), with Python 3, OpenSSH client, ADB and a wired LAN. A Raspberry Pi running ARM64 Debian is what was tested. Run this toolkit on the helper, **not on the NAS**.
  - **Linux:** needs root/sudo; `build` runs `build.py` directly.
  - **macOS:** install ADB with `brew install android-platform-tools`, plus Docker Desktop, OrbStack or Colima. `build` runs `build.py` inside a temporary, privileged `debian:trixie` ARM64 container. Only `plan.json`, the public SSH key and the three stock boot images go into the container. The Debian root is built on the container's own Linux filesystem, because macOS file sharing can't hold Linux ownership, device nodes or extended attributes. Only the boot images, root archive, manifest and host-key pins come back, and each is checked against the build manifest. Apple Silicon runs the container natively. Intel Macs run it under Docker's ARM64 emulation, which is much slower. The macOS path has not been tested end to end yet.
- At least **80 GiB free space** for a potentially incompressible full eMMC backup, critical backups, build trees and images. The tested mostly-empty NAS compressed to about 5.7 GB, but do not assume another one will.
- Stock Android 12/LincSeed, unlocked bootloader, SELinux Permissive, authorized ADB over the local network, and **stock boot slot B already running and marked successful**. Enable and authorize ADB at the NAS (see below). This toolkit does not unlock the bootloader or silently force an unknown stock B slot.
- The exact tested partition layout and stock boot B/U-Boot B/DTBO B hashes in `e1lib.py`. Other hardware revisions or firmware stop before flashing. Do not remove these guards to make an unfamiliar device proceed.
- A reserved/static NAS IP in your LAN, correct prefix/gateway/DNS, and physical power access. Keep the helper and backups on reliable storage. The install replaces the eMMC Android userdata filesystem; it does not format SATA disks.

No personal credentials, SSH keys, device-specific images or backups are included. Each private work directory gets a fresh owner SSH key, device identity, root UUID, image host keys and passwords. **Never distribute that work directory**, the resulting boot images, or the root archive: they contain authentication material.

Install helper prerequisites on Debian:

```sh
sudo apt-get update
sudo apt-get install adb openssh-client python3 sudo
```

On an **x86-64 helper**, `build` also installs `qemu-user` and `qemu-user-binfmt`, so the kernel can run the ARM64 programs inside the build root through QEMU emulation. Before building, it checks that the `qemu-aarch64` binfmt handler is enabled with the fix-binary (`F`) flag, and that ARM64 programs actually run in the new root. An emulated build is several times slower than a native one. Plain Debian on a PC or VM works; Docker containers and WSL may need binfmt set up on the host first. The x86-64 path has not been tested end to end yet.

`build` additionally installs debootstrap, GCC, libc headers, device-tree-compiler and kmod on the helper. It bootstraps a clean Debian root, uses signed Debian repositories and pins the tested `linux-image-6.12.113+deb13-arm64` package name. If that kernel is unavailable, the build stops; selecting another kernel requires separate validation.

## Enabling network ADB on the NAS

Follow the illustrated steps in the [README](../README.md#before-you-start-turn-on-adb-on-the-nas). In short:

1. With an HDMI monitor and USB keyboard on the NAS, press **Ctrl+N** at the LincOS kiosk screen to open Android Settings.
2. Join a **Wi-Fi network**, even when you use Ethernet. Android 12 only allows *Wireless debugging* while connected to Wi-Fi. The toolkit uses the wired address you give `init`.
3. In *Developer options*, turn on *Wireless debugging*, then click the **label** (not the switch) to open its screen. It shows a random `IP:port` and a *Pair device with pairing code* option.
4. From the helper: `adb pair IP:PAIRING_PORT` (enter the code), `adb connect IP:PORT`, then `adb tcpip 5555` and `adb connect NAS_IP:5555`. The toolkit expects port 5555; to use another, pass `init --adb-serial IP:PORT`.
5. In the LincOS firewall settings, allow inbound **TCP 5555** from your LAN subnet (e.g. `192.168.1.0/24`). If pairing is refused, the firewall may also be blocking the random wireless-debugging ports.
6. Accept the **"Allow debugging?"** prompt on the NAS screen, ticking *Always allow from this computer*. `adb devices` should list the NAS as `device`, not `unauthorized`.

**Network ADB resets whenever Android restarts.** After any reboot back into stock Android (for example the `return-stock` test), turn Wireless debugging on again, reconnect to the port it shows, and run `adb tcpip 5555` before running `root` again.

## Staged migration

Use a private directory outside this toolkit. Substitute your own NAS address, gateway, timezone and username below. Reserve the chosen address in your router first. The example IP is illustrative.

```sh
cd installer
WORK="$HOME/e1-private"
python3 e1-migrate.py --work "$WORK" init \
  --nas 192.168.1.50/24 --gateway 192.168.1.1 \
  --timezone America/Los_Angeles --user nas
python3 e1-migrate.py --work "$WORK" root
python3 e1-migrate.py --work "$WORK" backup
python3 e1-migrate.py --work "$WORK" build
```

### Choosing the extras

OpenMediaVault is always installed. When you run `init` in a terminal, it shows a checklist for the optional extras:

```
OpenMediaVault is always installed. Choose the extras:
  [x] 1  Desktop (LXDE on HDMI, started with startx)
  [x] 2    Web browser (Firefox ESR)
  [x] 3    Media players (VLC, mpv, FFmpeg, ALSA tools)
  [x] 4    Utilities (text editor, image viewer, archives, calculator, screenshots, htop)
  [x] 5    Remote desktop (VNC through an SSH tunnel)
Numbers to toggle (e.g. "3 5"), or Enter to accept:
```

Turning off the desktop (item 1) gives a headless NAS and turns off the app groups and VNC with it. To skip the checklist, pass the choices as flags instead:

| Flag | Effect |
| --- | --- |
| `--no-desktop` | Headless OMV only; no desktop, apps or VNC |
| `--desktop` | Install the LXDE desktop (the default) |
| `--apps web,media,utilities` | Choose app groups; also `all` (the default) or `none` |
| `--no-vnc` / `--vnc` | Skip or include tunneled VNC (included by default) |

Without a terminal and without flags, `init` installs everything. The choices are saved in `config.json`. You can change them right up to the last step by passing the same flags to `finish`, for example `finish --no-desktop`.

`root` uses the stock owner-authorized ADB connection and authenticated aria2 RPC to place a self-removing root cron job in LincSeed. It creates temporary, key-only SSH on NAS loopback port 2222, forwarded through ADB to helper port 22222. Its public host key is pinned using ADB. The cron job removes itself; the SSH listener lasts until reboot. The aria2 RPC secret is kept in memory and is not logged.

`backup` saves critical partitions, eMMC boot areas and a partition table, verifies critical files against source hashes, streams/compresses the entire eMMC, then re-reads/decompresses the saved file and compares its raw length/hash to the source stream. This is a **live stock backup**, not an offline filesystem-consistent snapshot. Keep it even though the migration only formats userdata. On an interrupted backup, preserve/move the partial backup directory before retrying; partial files are not silently overwritten.

Review `plan.json`, `backup/manifest.json`, `build/manifest.json`, and the device CID before the first write. All writes require an explicit `--write`; `install` additionally requires the exact CID. There is no automatic sequence that skips reboot checkpoints.

### 1. Test recovery A, preserving stock B

```sh
python3 e1-migrate.py --work "$WORK" stage-a --write
python3 e1-migrate.py --work "$WORK" reboot --from stock
# reboot waits for the NAS and prints the next command:
python3 e1-migrate.py --work "$WORK" verify-a
```

`reboot` waits for the NAS to come back (up to 5 minutes; change with `--timeout`, or skip with `--no-wait`). It detects whether RAM recovery, stock Android or installed Debian answered, and prints the next command. If the stage expected a different system, it says so: that means the bootloader fell back to the other slot. If nothing answers in time, it tells you to **unplug the power cable for 10 seconds**, plug it back in and switch it on, then keeps waiting. The E1 sometimes hangs on a software restart, and the front button doesn't fully cut power.

A is armed with **two tries**, not one. This bootloader decrements its counter before selection; a one-try setup can skip the intended slot. `verify-a` checks the new boot ID, expected device identity, board DT, RAM recovery marker and absence of disk mounts.

Test a normal restart back into stock B **before replacing B**:

```sh
python3 e1-migrate.py --work "$WORK" return-stock --write
python3 e1-migrate.py --work "$WORK" reboot --from recovery
# Back in Android; reauthorize/reconnect ADB if needed:
python3 e1-migrate.py --work "$WORK" root
python3 e1-migrate.py --work "$WORK" verify-stock
```

Then enter recovery A again:

```sh
python3 e1-migrate.py --work "$WORK" stage-a --write
python3 e1-migrate.py --work "$WORK" reboot --from stock
# reboot waits for recovery:
python3 e1-migrate.py --work "$WORK" verify-a
```

### 2. Install and boot recovery B

```sh
python3 e1-migrate.py --work "$WORK" stage-b --write
python3 e1-migrate.py --work "$WORK" reboot --from recovery
# reboot waits for recovery B:
python3 e1-migrate.py --work "$WORK" verify-b
```

B's stock image now exists in your verified backups; both on-device slots hold Linux RAM recovery. The already-verified recovery A is kept as fallback while B is written. Do not proceed if either recovery boot/reboot verification fails.

### 3. Install Debian into eMMC userdata

Copy the exact `emmc_cid` value from your private `plan.json`:

```sh
python3 e1-migrate.py --work "$WORK" install --write \
  --erase-emmc-userdata YOUR_EXACT_EMMC_CID
python3 e1-migrate.py --work "$WORK" reboot --from recovery
# reboot waits for installed Debian:
python3 e1-migrate.py --work "$WORK" verify-debian
python3 e1-migrate.py --work "$WORK" finish
```

The installer validates the eMMC CID, partition sizes/PARTUUID, matching recovery images and payload hashes. It formats **only p19**, extracts the verified root archive, checks it, unmounts/fscks it, writes and reads back installed boot A, and arms A while retaining successful recovery B. GPT, bootloader/trust/DTBO partitions and SATA disks are not rewritten. A failed validation stops the stage; inspect the output rather than repeatedly rerunning a destructive stage.

`finish` installs OMV first, then the extras you chose (desktop, app groups, VNC). It imports the prepared static Ethernet configuration, sets the MAC/timezone, creates your console user, sets unique passwords and tests OMV login. Output is saved privately in `finish.log`; credentials are in mode-0600 `LOGIN.txt` and `credentials.json`. Root remains SSH key-only; the console user can use sudo. The console and VNC password initially match, but later changes to one do not update the other.

OMV's official installation path is a minimal server and discourages desktop installations. This optional on-demand LXDE combination was exercised on the migrated E1; it is a custom combined NAS/desktop configuration, not an upstream-supported OMV desktop product. The installer refuses package removals or a conflicting display manager. SATA layout/shares are configured separately in OMV.

## Desktop and VNC

Log in locally as the configured console user and run:

```sh
startx
```

The base desktop provides LXDE's top menu/panel, PCManFM, LXTerminal and appearance/display/input settings. The app groups add Firefox ESR (`web`); VLC, mpv, FFmpeg and ALSA tools (`media`); and Mousepad, GPicView, Galculator, Xarchiver, scrot, zip/unzip/7zip and htop (`utilities`). Panel launchers, desktop icons and default apps are created only for installed groups. No display manager or automatic GUI boot is installed. Desktop disk automount/autorun is disabled so OMV manages storage.

On the original E1, Mali-G52/Panfrost hardware rendering was verified at 1080p. A 720p H.264 sample played through mpv with GPU rendering and **CPU video decoding**. VLC and mpv always decode on the CPU here, because Debian's FFmpeg can't drive the RK3568's stateless decoder. GStreamer can. To get hardware decoding of H.264/MPEG-2 (up to 1080p) and VP8 (up to 4K), run `sudo apt-get install --no-install-recommends gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav parole` and play videos in Parole, or another GStreamer-based player. `finish` and `install-desktop.sh` print this command when they finish, and it's in `~/Desktop-README.txt` on the NAS. GStreamer ranks the hardware decoder first, so they use it automatically. See [VALIDATION.md](VALIDATION.md#hardware-video-decoding) for measurements. There is no hardware HEVC/H.265, VP9 or 4K H.264 decoding with this kernel. 4K playback, populated NVMe slots and power-off remain unvalidated. These claims are distinct from the generic installer build test.

x11vnc shares the **active HDMI/X11 desktop**. It starts with LXDE, stops with the X session, and listens only on loopback port 5900. SSH allows the desktop user to forward only to `127.0.0.1:5900`. No desktop at the console means no VNC desktop yet.

From a computer with the generated private key and installed known-hosts file:

```sh
sh connect-vnc.sh nas@192.168.1.50 /path/to/e1-private/owner-key \
  /path/to/e1-private/installed-known_hosts
```

Leave the tunnel terminal open and connect your VNC viewer to `127.0.0.1:15900` (on macOS, open `vnc://127.0.0.1:15900`). Use the VNC password from `LOGIN.txt`. Port 5900 is intentionally not exposed on the LAN. VNC authentication and a complete 1920×1080 framebuffer transfer through this tunnel were tested on the original E1.

For an already-migrated Debian 13 system with an existing normal user, the independently reusable installers are:

```sh
sudo sh install-desktop.sh USER [--apps web,media,utilities|all|none]
sudo python3 setup-vnc.py USER
```

`setup-vnc.py` prompts for an eight-character VNC password; it does not place it in command arguments. The `--live` option can start it in an existing single Openbox/LXDE session. `install-desktop.sh USER --live` updates the panel/desktop while preserving open apps; the full LXDE session starts on the next `startx`.

## Fan curve

The kernel controls the fan from the CPU temperature, in three steps set by the device tree:

| Step | Fan level (of 255) | Speed |
| --- | --- | --- |
| Quiet | 20–90 | about 1,000–1,400 RPM |
| Medium | 130–170 | about 2,250 RPM at 170 |
| Full | 210–255 | |

The `lincstation-fan` service sets the CPU temperatures where each step starts, at every boot. There are three profiles:

| Profile | Quiet above | Medium above | Full above | Notes |
| --- | --- | --- | --- | --- |
| `quiet` | 25 °C | 50 °C | 60 °C | Quietest. In testing the drives settled around 38 °C at idle |
| `balanced` (default) | 25 °C | 45 °C | 55 °C | Quiet at idle (CPU around 38–41 °C), and speeds up sooner under load |
| `performance` | 25 °C | 35 °C | 45 °C | The upstream curve. Coolest drives (about 33 °C), but the fan runs at about 2,250 RPM even at idle |
| `custom` | your values | | | Uses `FAN_QUIET`, `FAN_MEDIUM` and `FAN_FULL` |

Switch profiles and check the result on the NAS:

```sh
sudo lincstation-fan performance     # or quiet, balanced, custom; saved and applied at every boot
lincstation-fan status               # profile, trip points, CPU temperature, fan speed (sudo adds drive temperatures)
```

For your own curve, edit `/etc/default/lincstation-fan`. Set `FAN_PROFILE=custom` and `FAN_QUIET`, `FAN_MEDIUM` and `FAN_FULL` in whole degrees Celsius, then run `sudo systemctl restart lincstation-fan`. The rule is `FAN_QUIET < FAN_MEDIUM < FAN_FULL < 70`. Invalid values are rejected, and the current curve stays in place.

Things to keep in mind:

- Below `FAN_QUIET` the fan stops completely. All profiles keep it at 25 °C, so the hard drives always get airflow.
- The curve only watches the CPU. After a change, check the drives with `sudo lincstation-fan status`; under about 45 °C is comfortable for them.
- The CPU still throttles at 70 °C and shuts down at 95 °C, whatever the profile.

## Kernel maintenance and recovery

This E1's stock bootloader reads Android-v2 boot partitions, not `/boot`. A normal Debian kernel install alone does not update that boot image.

The installed `lincstation-update-kernel` validates the device/root/recovery, builds a matching custom early startup and official modules, checks the image fits, saves/verifies old A, selects B while writing/verifying A, then arms A with two tries. It never writes B or reboots automatically.

Before enabling automatic kernel updates, validate one native rebuild on the new NAS:

```sh
sudo lincstation-update-kernel --install "$(uname -r)"
sudo systemctl reboot
# Reconnect after Debian boots successfully:
sudo lincstation-enable-kernel-hook
sudo apt-get install linux-image-arm64
```

The enable command checks a changed boot ID, the native image's full partition hash, successful A/B metadata and active boot-success/SSH service. The hook then rebuilds A after kernel package installs. Keep the initially tested kernel package/modules (marked manual), backups and private work directory. A larger or incompatible future kernel can still fail and require recovery.

To select preserved recovery B from installed Debian:

```sh
sudo lincstation-update-kernel --recovery
sudo systemctl reboot
```

Recovery uses your reserved NAS IP, key-only root SSH on port 2223 and `recovery-known_hosts`. It automatically mounts no disks. The early startup validates CID/root UUID before fsck/mount/switch_root; a pre-handoff error stays in authenticated RAM rescue. If a reboot hangs, disconnect power for ten seconds and retry; do not assume a front-button press removed power.

Wi-Fi and Bluetooth come from a Realtek RTL8822CS module. Debian's `rtw88_8822cs` and `btrtl` drivers handle it, using firmware from `firmware-realtek`, and the base system includes `iw`, `bluez` and `wireless-regdb`. The device tree keeps the module's `vcc_wl`/`vccio_wl` supplies always on, as the stock firmware does. The early boot environment carries the module's firmware and re-probes the SDIO controller if Wi-Fi wasn't detected. Join a Wi-Fi network in OMV's network settings or with `wpa_supplicant`; that step hasn't been tested yet. See [VALIDATION.md](VALIDATION.md#wi-fi-and-bluetooth).

The tested restart fix removes the RK809 PMIC `system-power-controller` property from the DT, allowing PSCI firmware restart. The stock-compatible `reboot_mode` symbol is retained for DTBO application. Both the Android header DTB and Rockchip resource DTB are replaced. `/init` must be executable (0755); this is explicitly checked and tested. Power-off behavior has not been proven with this DT change.

If boot A fails, B remains the recovery route. Use a verified previous full A image from `/var/lib/lincstation/` or your private build directory only after checking CID, partition size and image hash. Automatic full Android restoration is intentionally not provided: a full-eMMC restore is a separate operation that must account for the live system and exact backup target. Original eMMC boot-area backups are retained as well.

## Validation and sources

Run the non-device tests from `installer/`:

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile *.py
sh -n install-desktop.sh
sh -n connect-vnc.sh
```

They exercise A/B CRC/sector preservation, two-try encoding, image limits, executable CPIO init and device nodes, plus refusal to write on wrong CID/firmware. They do not simulate every bootloader or power-loss condition. See [VALIDATION.md](VALIDATION.md) for measured results and limits.

`rebuild-dtb.sh NEW_DIRECTORY` builds the supplied patched DTS with the included Linux v6.12.113 dependencies. The installer uses the separately SHA-256-pinned tested DTB. Vendor logos and stock DTBO are extracted from each recipient's own verified firmware backup. See `assets/SOURCES.json`, `assets/kernel-tree/dependency-sources.json`, [THIRD-PARTY.md](../THIRD-PARTY.md) and [LICENSES/](../LICENSES/) for provenance and licenses.

Primary references: [OMV on Debian](https://docs.openmediavault.org/en/8.x/installation/on_debian.html), [Debian x11vnc manual](https://manpages.debian.org/trixie/x11vnc/x11vnc.1.en.html), [OpenSSH server configuration](https://man.openbsd.org/sshd_config), [AOSP mkbootimg](https://android.googlesource.com/platform/system/tools/mkbootimg/), [Rockchip resource tool](https://github.com/rockchip-linux/u-boot/blob/next-dev/tools/rockchip/resource_tool.c).
