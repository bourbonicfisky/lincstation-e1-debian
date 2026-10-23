#!/bin/sh
set -eu
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=${1:?Usage: ./rebuild-dtb.sh NEW_OUTPUT_DIRECTORY}
[ ! -e "$out" ] || { echo 'Choose a new output directory'; exit 1; }
mkdir -p "$out"
cpp -nostdinc -undef -D__DTS__ -x assembler-with-cpp \
  -I "$base/assets/kernel-tree/include" \
  -I "$base/assets/kernel-tree/arch/arm64/boot/dts/rockchip" \
  "$base/assets/e1-board.dts" > "$out/board.pp.dts"
dtc -@ -I dts -O dtb -o "$out/board.dtb" "$out/board.pp.dts"
sha256sum "$out/board.dtb"
echo 'The installer uses the separately hash-pinned, hardware-tested assets/e1-tested-board.dtb.'
