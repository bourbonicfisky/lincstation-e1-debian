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

## Limits

The generalized root-access/backup/flash/finish sequence has not been executed end to end on a second stock E1. The tested images above were not booted on hardware. The manual hardware path and individual desktop/VNC setup were exercised on the original NAS; that does not prove every newly generalized stage or recipient firmware variant.

Do not infer support for other E1 firmware hashes, board revisions, kernel versions, power-off, hardware video decoding, 4K playback, Wi-Fi, NVMe population, or automatic Android restoration. On-device writes intentionally require explicit stages and matching identities, and unknown stock firmware is rejected.
