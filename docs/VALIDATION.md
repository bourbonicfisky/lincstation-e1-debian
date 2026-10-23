# Validation — 2026-10-22

## Original migrated E1

- Debian 13.7 ARM64, Linux 6.12.113+deb13-arm64, OMV 8.5.12-1.
- Normal boot of the corrected native rebuilt installed image returned in 72 seconds; installed root and SSH/OMV/boot-success services verified, A marked successful, recovery B preserved.
- HDMI 1920×1080/60 Hz, direct Mali-G52/Panfrost rendering with Mesa 25.0.7.
- 720p H.264/AAC test completed using mpv GPU rendering and CPU video decode; HDMI ALSA initialized. Test audio was silent, so audible output was not confirmed.
- LXDE panel/desktop applied live without closing user applications; complete LXDE selected for next `startx`. VLC, Firefox ESR and listed basics installed. No graphical display manager.
- x11vnc 0.9.17 bound to loopback only. SSH tunnel, VNC password authentication and all 2,073,600 framebuffer pixels verified. Approximately 19 MiB process RSS. No synthetic input was injected into the user's active session.
- No failed systemd units at the final read-only check.

## Reusable toolkit build and tests

A clean debootstrap build ran on a Debian 13 ARM64 helper using **new test keys, a fictitious CID/MAC and a documentation-only NAS IP**. It did not flash or reboot the working NAS.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Recovery image | 143,316,992 | `e9a515cd770e9f55eac9fe9fdc77b99b001971be31cd3d31ca103ecd67a5d25b` |
| Installed boot image | 143,316,992 | `6a5f633f098d9fcf603d1c4ffbcaad7e2ad739ff7e0987f0f06619f38259e511` |
| Initial test root archive | 308,273,695 | `d6b2ba13748f390aacc0907b797df95bc76d7fd8398b4b34403f0005817c4ed7` |

These are **private test artifacts, not downloads or images to flash**. Recipient builds have different keys, UUIDs, identities and hashes. Both test boot images fit the 157,286,400-byte partitions, with 13,969,408 bytes remaining.

- RAM SSH configuration and required Python imports passed in the recovery chroot.
- Both actual compressed CPIO archives were parsed and confirmed to contain executable 0755 `/init` and BusyBox.
- Stock DTBO application passed and did not reintroduce `system-power-controller`.
- The included device-tree sources/dependencies compiled successfully. Rebuilt DTB SHA was `cff5da79bfefe04a41858032db0c0c2e0c8bec422a5aca6d533bb8ea2628f8be`; decompiling the rebuilt and hardware-tested DTBs produced **identical DTS text**. Binary hashes differ due to representation, so the installer continues using the independently pinned tested binary.
- Eight guard/format tests passed on macOS and Debian ARM64. Python compilation and shell syntax checks passed.
- Final maintenance-helper additions compiled in the clean target root; installed SSH configuration validated and dpkg audit was clean. These additions were checked after the initial archive build, so that archive's hash above identifies the initial test artifact.
- Build publication ownership was corrected and checked: the non-root helper user can read manifests, images, root archive and host-key pins; extracted rootfs ownership remains intact.

## macOS helper build (Intel Mac, Docker Desktop)

The `build` stage ran through the macOS container path on an Intel Mac. Docker Desktop emulated ARM64 for the whole build, which took about 48 minutes. It used the tested unit's stock boot images, a new SSH key, a made-up eMMC ID and MAC address, and a documentation-only IP address. Nothing was flashed.

| Artifact | Bytes |
| --- | ---: |
| Recovery image | 143,413,248 |
| Installed boot image | 143,415,296 |
| Root archive | 308,405,501 |

- All three artifacts matched the build manifest's hashes after being copied out of the container.
- Both images fit the 157,286,400-byte boot partition, and each contains the hash-pinned tested DTB.
- The kernel was byte-identical to the one booted on the E1 (37,728,192 bytes).
- Both RAM disks contain an executable 0755 `/init`, BusyBox, SSH, Python 3.13 with its shared libraries, and the kernel modules. The recovery Python ran inside the build.

Running the build in emulation turned up four problems that a native Pi build hides, all now fixed:

- The minimal Debian image has no CA certificates, so HTTPS downloads failed.
- The build root used the NAS's DNS server, which may not be reachable from the helper.
- The helper lacked `systemctl` and `ssh-keygen`.
- `ldd` crashes under QEMU, which silently left out Python's libraries. Libraries are now found with `readelf`, and a missing library stops the build.

The x86-64 Linux path uses the same emulation, but it hasn't been run end to end. Apple Silicon Macs run the container natively and haven't been tested yet either.

## CPU benchmark (Geekbench 6)

| Single-core | Multi-core | Result |
| ---: | ---: | --- |
| **230** | **605** | [browser.geekbench.com/v6/cpu/19377989](https://browser.geekbench.com/v6/cpu/19377989) |

- Geekbench 6.7.1 Preview for Linux AArch64, the official ARM64 build. Run on October 22, 2026, it took 28 minutes 10 seconds.
- Debian 13 with kernel `6.12.113+deb13-arm64`, 4 cores, and 3.81 GB RAM. The `schedutil` governor was left at its default, with a 1.992 GHz maximum.
- Peak sampled SoC temperature was 52.5 °C.
- OMV, the HDMI desktop and VNC were left running. This is one live-system run, not an average of isolated runs.
- SSH, nginx and the OMV engine were active afterwards, with no failed systemd units.

## Fan curve

The upstream device tree's fan trips are at 25, 35 and 45 °C. On the migrated E1 the CPU idled at 36–37 °C, so the fan ran at pwm 170/255, about 2,230 RPM. Moving the trips to 25, 50 and 60 °C at runtime gave these results:

| Time | CPU | Fan | Drives (sda/sdb) |
| --- | --- | --- | --- |
| Before | 37 °C | pwm 170, 2,226 RPM | 33/33 °C |
| +1 min | 34 °C | pwm 50, 1,259 RPM | 33/33 °C |
| +2 min | 34 °C | pwm 90, 1,348 RPM | 33/34 °C |
| +3 min | 35 °C | pwm 90, 1,378 RPM | 34/34 °C |

The drives are WD Red Plus 4 TB (WD40EFPX, 5,400 RPM). The `lincstation-fan` service replaced deliberately restored upstream trips with the configured ones. An invalid config (medium at 80 °C) was rejected, and the trips were left unchanged. These were short idle measurements. Drive temperatures under sustained load with the quieter curve haven't been measured yet.

## Wi-Fi and Bluetooth

The E1 uses a Realtek **RTL8822CS** module: Wi-Fi over SDIO (`mmc1`, ID `024c:c822`) and Bluetooth over `uart1` with the H5 protocol. The stock Android device tree identifies it as `rtl8822cs`.

**What was wrong.** The upstream E1 device tree used the module's `vcc_wl` and `vccio_wl` GPIO regulators as switchable `vmmc`/`vqmmc` SDIO supplies. In that setup the card timed out during initialisation (`error -110`, then `Unexpected CMD11 timeout`), so Wi-Fi never appeared. The stock firmware keeps both supplies always on and doesn't attach them to the SDIO controller. Two more problems followed: the drivers load in the early boot environment, which only carried Ethernet firmware, and SDIO start-up occasionally failed at boot.

**Changes:**

- The device tree marks `vcc_wl` and `vccio_wl` `regulator-always-on`/`regulator-boot-on`, and drops `vmmc-supply`/`vqmmc-supply` from `sdmmc1`. A structural comparison of the binaries shows exactly these six property changes from the previous tested DTB. Stock DTBO overlays still apply, and the PMIC `system-power-controller` removal is intact. The new DTB SHA-256 is `1fce124bfe67804135ad04f40756754aa7b149fab9794a9dfc3f2716848da933`.
- The early boot environment includes `rtw88/rtw8822c_fw.bin`, `rtw88/rtw8822c_wow_fw.bin`, `rtl_bt/rtl8822cs_fw.bin` and `rtl_bt/rtl8822cs_config.bin`.
- If no SDIO card has appeared by the end of early boot, the init script re-probes the SDIO controller up to three times.
- `iw`, `bluez` and `wireless-regdb` are now in the base system.

**Results on the migrated E1:**

- Re-probing the SDIO controller succeeded 6 times out of 6. Each time the link settled at 50 MHz high speed; SDR104 wasn't reached, so Wi-Fi throughput may be lower than under stock Android.
- Across three consecutive reboots with all changes in place, `wlan0` and `hci0` came up automatically every time. Each boot took about 55–60 seconds, with no failed systemd units.
- Wi-Fi firmware 9.9.15 loaded. A scan found 29 networks on both 2.4 GHz and 5 GHz, with signals up to −21 dBm.
- Bluetooth firmware `0xb5d66dcb` and its config loaded. The controller `hci0` powered on, and a 12-second scan found 15 devices.
- Not yet tested: joining a Wi-Fi network, throughput, Bluetooth pairing, and audio.

## Hardware video decoding

Tested on the migrated E1 (Debian kernel 6.12.113, GStreamer 1.26), after installing `gstreamer1.0-plugins-bad`, `gstreamer1.0-plugins-good`, `gstreamer1.0-libav`, `gstreamer1.0-tools` and `v4l-utils`. The APT dry run removed nothing.

The kernel's `hantro_vpu` driver exposes the decoder as `/dev/video0`, the encoder as `/dev/video1`, and the RGA 2D block as `/dev/video2`. The decoder reports:

| Codec | Max resolution |
| --- | --- |
| H.264 | 1920×1088 |
| MPEG-2 | 1920×1088 |
| VP8 | 3840×2160 |

It outputs NV12. The board's device tree has no `rkvdec` node, so there's no hardware HEVC/H.265 or VP9 decoding, and no H.264 above 1080p.

A 20-second 1080p30 H.264 High-profile clip (600 frames), decoded to `fakesink`:

| Test | Hardware (`v4l2slh264dec`) | Software (`avdec_h264`) |
| --- | --- | --- |
| Fastest possible decode | 38 fps, 21% of total CPU | 79 fps, 80% of total CPU |
| Real-time playback at 30 fps | 17% of total CPU | 33% of total CPU |

- All 600 hardware-decoded frames were bit-identical to the software decode (SHA-1 per frame after conversion to I420).
- The hardware decoder halves CPU use during normal playback, but it's slower than four-core software decoding at full speed. Here it was enough for 1080p30, not 1080p60.
- GStreamer ranks `v4l2slh264dec` (primary + 1) above `avdec_h264` (primary), and `playbin` chose the hardware decoder automatically.
- VLC and mpv decode through Debian's FFmpeg, which supports only stateful V4L2 decoders, so they can't use this one.
- Parole was installed (4 packages, nothing removed), but it wasn't launched against a display. Its automatic decoder choice comes from the `playbin` test above.

## Limits

The generalized root-access/backup/flash/finish sequence has not been executed end to end on a second stock E1. The tested images above were not booted on hardware. The manual hardware path and individual desktop/VNC setup were exercised on the original NAS; that does not prove every newly generalized stage or recipient firmware variant.

Do not infer support for other E1 firmware hashes, board revisions, kernel versions, power-off, hardware decoding beyond the tested H.264 path, 4K playback, Wi-Fi association or throughput, Bluetooth pairing, NVMe population, or automatic Android restoration. On-device writes intentionally require explicit stages and matching identities, and unknown stock firmware is rejected.
