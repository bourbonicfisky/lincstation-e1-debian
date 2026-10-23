# Source and license notes

- `installer/assets/mkbootimg.py`, `installer/assets/unpack_bootimg.py` and `installer/assets/gki/generate_gki_certificate.py`: AOSP mkbootimg tooling, Apache License 2.0. Upstream notices remain in the files; license text is in `LICENSES/Apache-2.0`.
- `installer/assets/resource_tool.c`: Rockchip U-Boot resource image utility, copyright 2008–2015 Fuzhou Rockchip Electronics Co., Ltd; GPL-2.0-or-later. The source is included and compiled locally; GPL v2 text is in `LICENSES/GPL-2`.
- `installer/assets/e1-board.dts`: E1 board source from the commit identified in `installer/assets/SOURCES.json`, adapted to Linux v6.12.113 includes, with stock DTBO compatibility (`chosen`/`reboot_mode`), the tested PMIC restart change, and always-on Wi-Fi module supplies. SPDX GPL-2.0-or-later OR MIT; distributed here under the GPL option. The tested compiled DTB is `installer/assets/e1-tested-board.dtb`.
- `installer/assets/kernel-tree/`: complete version-matched include files used by the patched DTS. Original notices/SPDX identifiers are retained; exact upstream URLs are in `dependency-sources.json`. These Linux sources and the derived DTB are distributed under GPL v2 where that option is offered; individual source headers retain their additional permissive alternatives.
- Original migration/desktop/VNC glue in `installer/` is provided under the MIT license in `LICENSE`. No warranty is offered.

Debian packages are fetched from their signed repositories and are not redistributed here. Recipient stock firmware, logos, backups, root archives and generated private keys are not part of this public bundle.
