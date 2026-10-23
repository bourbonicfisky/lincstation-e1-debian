#!/usr/bin/env python3
"""Run on installed NAS only after rebooting a native lincstation-update-kernel image."""
import json,os,shutil,subprocess
from pathlib import Path
from e1lib import require,sha,read_ab,run
require(os.geteuid()==0,'Run as root')
p=json.loads(Path('/etc/lincstation-install.json').read_text())
require(run('findmnt','-n','-o','UUID','/')==p['root_uuid'],'Wrong root')
require(Path('/sys/block/mmcblk0/device/cid').read_text().strip()==p['emmc_cid'],'Wrong eMMC')
m=json.loads(Path('/var/lib/lincstation/boot-'+os.uname().release+'.json').read_text())
require(m['installed'] and m['boot_id']!=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'Reboot the native-built image first')
require(sha('/dev/mmcblk0p11')==m['padded_sha256'] and sha('/dev/mmcblk0p12')==m['recovery_b_sha256'],'Boot/recovery hashes changed')
subprocess.run(['systemctl','is-active','--quiet','lincstation-boot-success','ssh'],check=True)
with open('/dev/mmcblk0p6','rb') as f:f.seek(2048);a,b=read_ab(f.read(512))
require(a[2]==1 and b[2]==1,'Both slots must be marked successful')
shutil.copy2('/usr/local/lib/lincstation/kernel-hook.pending','/etc/kernel/postinst.d/zzzz-lincstation-boot')
print('Kernel hook enabled after verified native-image reboot. You may now install the linux-image-arm64 metapackage.')
