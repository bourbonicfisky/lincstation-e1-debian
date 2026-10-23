# Notes for AI coding agents

This repository has what an agent needs to run a LincStation E1 migration: the staged CLI in `installer/e1-migrate.py`, the full procedure in [docs/INSTALL.md](docs/INSTALL.md), and the tested limits in [docs/VALIDATION.md](docs/VALIDATION.md). Read INSTALL.md completely before running anything against a NAS.

## Run the stages in order

`init → root → backup → build → stage-a → reboot → verify-a → return-stock → reboot → root → verify-stock → stage-a → reboot → verify-a → stage-b → reboot → verify-b → install → reboot → verify-debian → finish`

`python3 e1-migrate.py --work WORK status` shows which stages have completed. After each `reboot`, the CLI prints which system came back and the next command to run.

## Steps that need the human

Stop and ask the user to do these:

- **Turn on network ADB** at the NAS: HDMI monitor and keyboard, Ctrl+N, Wi-Fi, Wireless debugging, pairing, the firewall rule, and accepting the "Allow debugging?" prompt. See the README. This has to be redone after every reboot back into Android.
- **Power cycles.** If `reboot` reports that the NAS hasn't come back, ask the user to unplug the power cable for 10 seconds, plug it back in, and switch it on. Never treat a power cycle as a successful software reboot.
- **Software choices** at `init`: headless, or the desktop with app groups and VNC.
- **Confirmation before every destructive stage.** `stage-a`, `stage-b`, `return-stock` and `install` need `--write`. `install` also needs `--erase-emmc-userdata` with the exact eMMC CID, and erases the Android userdata partition. Show the user the stage and the CID, and wait for an explicit yes.

## Never do these

- Remove or weaken guards: stock firmware hashes, CID and partition checks, `--write`, or the verify-before-next-stage files.
- Arm a boot slot with one try. This bootloader needs **two**.
- Write the bootloader, GPT, DTBO or slot B outside the provided stages, or touch the SATA disks.
- Rerun a failed destructive stage blindly. Read its output and report it to the user.
- Commit, print or upload anything from the private work directory: SSH keys, `credentials.json`, `LOGIN.txt`, backups or built images.

## Developing the toolkit

Run `cd installer && python3 -m unittest discover -s tests -v` and `python3 -m py_compile *.py` after any change. Keep `install-desktop.sh` app group names in sync with `APP_GROUPS` in `e1lib.py`.
