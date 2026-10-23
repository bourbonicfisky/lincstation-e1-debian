#!/usr/bin/env python3
"""Build private, per-device Debian/root and recovery images on a Debian 13 ARM64 or x86-64 helper."""
import json,os,re,shutil,stat,subprocess,sys,time
from pathlib import Path
from e1lib import *
BASE=Path(__file__).resolve().parent

def build(work):
    machine=os.uname().machine;emulated=machine!='aarch64'
    require(os.geteuid()==0,'Build as root on the Linux helper')
    require(machine in ('aarch64','x86_64'),'Unsupported helper architecture '+machine+'; use ARM64 or x86-64 Linux')
    require('VERSION_ID="13"' in Path('/etc/os-release').read_text(),'Debian 13 helper required')
    os.umask(0o077);plan=json.loads((work/'plan.json').read_text());out=work/'build'
    require(not out.exists(),'Build directory exists; preserve it and choose a fresh work build directory before retrying')
    for name,digest in STOCK.items():require(sha(work/'backup'/name)==digest,'Stock backup hash mismatch')
    require(sha(BASE/'assets/e1-tested-board.dtb')==DTB_SHA,'Tested DTB mismatch')
    require(shutil.disk_usage(work).free>8*1024**3,'At least 8 GiB free required for build')
    out.mkdir(mode=0o700);root=out/'rootfs';ram=out/'ram';assets=out/'boot-assets'
    env=dict(os.environ,DEBIAN_FRONTEND='noninteractive',LC_ALL='C')
    subprocess.run(['apt-get','update'],env=env,check=True)
    subprocess.run(['apt-get','-y','--no-install-recommends','install','ca-certificates','debootstrap','gcc','binutils','libc6-dev','device-tree-compiler','kmod','openssh-client',*(['qemu-user','qemu-user-binfmt'] if emulated else [])],env=env,check=True)
    if emulated:
        # x86-64 helper: the kernel hands ARM64 binaries to QEMU. The F (fix-binary) flag lets
        # chrooted ARM64 programs run without copying the emulator into the target root.
        handler=Path('/proc/sys/fs/binfmt_misc/qemu-aarch64')
        if not handler.is_file():subprocess.run(['systemctl','restart','systemd-binfmt'],check=False)
        require(handler.is_file(),'QEMU aarch64 binfmt handler missing; is binfmt_misc mounted? (containers and WSL may need host setup)')
        info=handler.read_text();flags=re.search(r'^flags:\s*(\S*)',info,re.M)
        require(info.startswith('enabled') and flags and 'F' in flags.group(1),'QEMU aarch64 binfmt handler must be enabled with the F flag')
        print('x86-64 helper: building the ARM64 root through QEMU user emulation; this is slower than a native ARM64 build.')
    subprocess.run(['debootstrap','--arch=arm64','--variant=minbase','--include=ca-certificates','trixie',str(root),'https://deb.debian.org/debian'],env=env,check=True)
    require(run('chroot',root,'/usr/bin/uname','-m')=='aarch64','ARM64 programs do not run in the build root')
    def put(path,text,mode=0o644):
        f=root/path;f.parent.mkdir(parents=True,exist_ok=True)
        if f.is_symlink():f.unlink()
        f.write_text(text);f.chmod(mode)
    def chroot(*args):subprocess.run(['chroot',str(root),'/usr/bin/env','DEBIAN_FRONTEND=noninteractive','LC_ALL=C',*args],check=True)
    put('usr/sbin/policy-rc.d','#!/bin/sh\nexit 101\n',0o755)
    put('etc/apt/sources.list','deb https://deb.debian.org/debian trixie main non-free-firmware\ndeb https://deb.debian.org/debian trixie-updates main non-free-firmware\ndeb https://security.debian.org/debian-security trixie-security main non-free-firmware\n')
    # Resolve through the helper's DNS while building; the NAS's own DNS server may not be reachable from here.
    put('etc/resolv.conf',Path('/etc/resolv.conf').read_text())
    # No helper /dev bind mount: debootstrap supplies device nodes. No services start in the chroot.
    chroot('apt-get','update')
    chroot('apt-get','-y','--no-install-recommends','install','linux-image-'+KERNEL,'busybox-static','kmod','openssh-server','systemd-sysv','udev','python3','iproute2','e2fsprogs','tar','curl','sudo','systemd-resolved','systemd-timesyncd','firmware-realtek','ethtool','btrfs-progs','smartmontools','initramfs-tools','gnupg','psmisc')
    chroot('apt-mark','manual','linux-image-'+KERNEL)
    put('etc/hostname','lincstation\n');put('etc/hosts','127.0.0.1 localhost\n127.0.1.1 lincstation\n::1 localhost ip6-localhost ip6-loopback\n')
    put('etc/fstab','UUID='+plan['root_uuid']+' / ext4 defaults,noatime 0 1\n')
    put('etc/lincstation-install.json',json.dumps(plan,indent=2)+'\n',0o600)
    put('root/.ssh/authorized_keys',(work/'owner-key.pub').read_text(),0o600);(root/'root').chmod(0o700);(root/'root/.ssh').chmod(0o700)
    put('etc/ssh/sshd_config.d/10-lincstation.conf','PermitRootLogin prohibit-password\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nPubkeyAuthentication yes\n')
    # Every build has unique SSH host keys, including recovery.
    for f in (root/'etc/ssh').glob('ssh_host_*'):f.unlink()
    chroot('ssh-keygen','-A');chroot('passwd','-l','root')
    put('etc/systemd/network/10-lincstation.link','[Match]\nDriver=r8169\n[Link]\nNamePolicy=\nName=eth0\nMACAddressPolicy=none\nMACAddress='+plan['factory_mac']+'\n')
    put('etc/systemd/network/80-lincstation.network','[Match]\nName=eth0\n[Network]\nAddress='+plan['nas_ip']+'/'+str(plan['prefix'])+'\nGateway='+plan['gateway']+'\nDNS='+plan['dns']+'\n')
    put('etc/network/interfaces','auto lo\niface lo inet loopback\n\nauto eth0\niface eth0 inet static\n    address '+plan['nas_ip']+'/'+str(plan['prefix'])+'\n    gateway '+plan['gateway']+'\n    dns-nameservers '+plan['dns']+'\n')
    put('usr/local/sbin/lincstation-boot-success',(BASE/'templates/lincstation-boot-success').read_text(),0o755)
    put('etc/systemd/system/lincstation-boot-success.service',(BASE/'templates/lincstation-boot-success.service').read_text())
    chroot('systemctl','enable','ssh','systemd-networkd','systemd-resolved','systemd-timesyncd','lincstation-boot-success')
    (root/'run/sshd').mkdir(exist_ok=True);chroot('/usr/sbin/sshd','-t')
    for directory in ['bin','sbin','usr/bin','usr/sbin','proc','sys','dev/pts','run/sshd','tmp','www','etc/ssh','root/.ssh','lib/modules','lib/firmware','mnt']:(ram/directory).mkdir(parents=True,exist_ok=True)
    for d in ram.rglob('*'):
        if d.is_dir():d.chmod(0o755)
    (ram/'tmp').chmod(0o1777);(ram/'root').chmod(0o700);(ram/'root/.ssh').chmod(0o700)
    def copyfile(name,dest=None):
        src=root/name.lstrip('/');dst=ram/(dest or name).lstrip('/');dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst,follow_symlinks=True)
    # Resolve shared libraries by reading ELF headers with readelf, not by running ldd:
    # ldd executes target code, which can crash under QEMU emulation (x86-64 helpers, Intel Macs).
    libdirs=['lib/aarch64-linux-gnu','usr/lib/aarch64-linux-gnu','lib','usr/lib'];copied=set()
    def binary(name,dest=None):
        copyfile(name,dest);queue=[name]
        while queue:
            current=queue.pop();info=run('readelf','-dlW',root/current.lstrip('/'))
            for interp in re.findall(r'program interpreter: (/[^\]]+)\]',info):
                if interp not in copied:copied.add(interp);copyfile(interp)
            for lib in re.findall(r'\(NEEDED\)\s+Shared library: \[([^\]]+)\]',info):
                found=next(('/'+d+'/'+lib for d in libdirs if (root/d/lib).is_file()),None)
                require(found,'Shared library '+lib+' needed by '+current+' is missing from the build root')
                if found not in copied:copied.add(found);copyfile(found);queue.append(found)
    binary('/usr/bin/busybox','/bin/busybox');binary('/usr/bin/kmod','/sbin/modprobe')
    for name in ['/usr/sbin/sshd','/usr/lib/openssh/sshd-auth','/usr/lib/openssh/sshd-session','/usr/sbin/e2fsck','/usr/sbin/mkfs.ext4','/usr/sbin/blkid','/usr/sbin/blockdev','/usr/bin/python3.13','/usr/bin/tar']:binary(name)
    shutil.copytree(root/'usr/lib/python3.13',ram/'usr/lib/python3.13',symlinks=True)
    if (root/'etc/python3.13').exists():shutil.copytree(root/'etc/python3.13',ram/'etc/python3.13')
    for so in (root/'usr/lib/python3.13').rglob('*.so'):binary('/'+str(so.relative_to(root)))
    (ram/'usr/bin/python3').symlink_to('python3.13')
    for name in ['sh','false']:(ram/'bin'/name).symlink_to('busybox')
    shutil.copytree(root/'lib/modules'/KERNEL,ram/'lib/modules'/KERNEL,symlinks=True)
    shutil.copytree(root/'lib/firmware/rtl_nic',ram/'lib/firmware/rtl_nic',symlinks=True)
    subprocess.run(['depmod','-b',str(ram),KERNEL],check=True)
    for f in (ram/'lib/modules'/KERNEL).glob('modules.*'):f.chmod(0o644)
    def rput(path,text,mode=0o644):f=ram/path;f.write_text(text);f.chmod(mode)
    rput('etc/passwd','root:x:0:0:root:/root:/bin/sh\nsshd:x:100:65534:sshd:/run/sshd:/bin/false\n')
    rput('etc/group','root:x:0:\nnogroup:x:65534:\n');rput('etc/shadow','root:NP:20000:0:99999:7:::\nsshd:!:20000:0:99999:7:::\n',0o600)
    rput('etc/nsswitch.conf','passwd: files\ngroup: files\nshadow: files\nhosts: files dns\n');rput('etc/hosts','127.0.0.1 localhost\n');rput('etc/resolv.conf','nameserver '+plan['dns']+'\n')
    rput('etc/e1-recovery',plan['root_uuid']+'\n');rput('root/.ssh/authorized_keys',(work/'owner-key.pub').read_text(),0o600)
    subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(ram/'etc/ssh/ssh_host_ed25519_key')],check=True)
    rput('etc/ssh/sshd_config','Port 2223\nHostKey /etc/ssh/ssh_host_ed25519_key\nPidFile /run/sshd.pid\nAuthorizedKeysFile /root/.ssh/authorized_keys\nPermitRootLogin prohibit-password\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nPubkeyAuthentication yes\nUsePAM no\nAllowUsers root\nAllowTcpForwarding no\nX11Forwarding no\nPermitTunnel no\nSubsystem sftp internal-sftp\n')
    os.mknod(ram/'dev/null',stat.S_IFCHR|0o666,os.makedev(1,3))
    subprocess.run(['chroot',str(ram),'/usr/sbin/sshd','-t'],check=True)
    subprocess.run(['chroot',str(ram),'/usr/bin/python3','-c','import json,hashlib,zlib,subprocess;print("RAM Python validated")'],check=True)
    tokens={'@MAC@':plan['factory_mac'],'@ADDRESS@':plan['nas_ip']+'/'+str(plan['prefix']),'@GATEWAY@':plan['gateway'],'@ROOT_UUID@':plan['root_uuid'],'@CID@':plan['emmc_cid'],'@EPOCH@':str(int(time.time()))}
    def init(kind):
        s=(BASE/'templates'/kind).read_text()
        for k,v in tokens.items():s=s.replace(k,v)
        require(not re.search('@[A-Z_]+@',s),'Unexpanded early-init token')
        rput('init',s,0o755);subprocess.run([str(ram/'bin/busybox'),'sh','-n',str(ram/'init')],check=True)
    for d in ram.rglob('*'):
        if d.is_dir() and not d.is_symlink():d.chmod(0o755)
    (ram/'root').chmod(0o700);(ram/'root/.ssh').chmod(0o700);(ram/'tmp').chmod(0o1777)
    assets.mkdir();stock=out/'stock-boot';subprocess.run([sys.executable,str(BASE/'assets/unpack_bootimg.py'),'--boot_img',str(work/'backup/boot_b.img'),'--out',str(stock)],check=True)
    resource_tool=out/'resource_tool';subprocess.run(['gcc','-O2',str(BASE/'assets/resource_tool.c'),'-o',str(resource_tool)],check=True)
    resource=out/'resource';subprocess.run([str(resource_tool),'--unpack','--image='+str(stock/'second'),str(resource)],check=True)
    shutil.copy2(BASE/'assets/e1-tested-board.dtb',assets/'board.dtb');shutil.copy2(assets/'board.dtb',resource/'rk-kernel.dtb')
    subprocess.run([str(resource_tool),'--pack','--image='+str(assets/'resource.img'),'rk-kernel.dtb','logo.bmp','logo_kernel.bmp'],cwd=resource,check=True)
    shutil.copy2(stock/'recovery_dtbo',assets/'recovery_dtbo')
    # Android dt_table_header/entries: retain and validate every stock overlay.
    import struct
    table=(assets/'recovery_dtbo').read_bytes();magic,total,header,entry,n,offset,page,version=struct.unpack_from('>8I',table)
    require(magic==0xd7b7ab1e and total<=len(table) and entry>=32 and 0<n<32,'Unexpected Android DTBO table')
    overlays=[]
    for i in range(n):
        length,position=struct.unpack_from('>II',table,offset+i*entry);require(position+length<=total,'Invalid DTBO bounds')
        f=out/('overlay-'+str(i)+'.dtbo');f.write_bytes(table[position:position+length]);overlays.append(str(f))
    subprocess.run(['fdtoverlay','-i',str(assets/'board.dtb'),'-o',str(out/'overlay-applied.dtb'),*overlays],check=True)
    dts=run('dtc','-I','dtb','-O','dts',out/'overlay-applied.dtb',stderr=subprocess.DEVNULL)
    require('system-power-controller' not in dts,'PMIC power-controller property reintroduced')
    def pack(kind,installed=False):
        init('installed-init' if installed else 'recovery-init');cpio(ram,out/(kind+'.cpio.gz'))
        cmdline='console=ttyS2,1500000n8 earlycon=uart8250,mmio32,0xfe660000 '
        cmdline+=('root=UUID='+plan['root_uuid']+' rootfstype=ext4 rootwait rw panic=15 net.ifnames=0 rdinit=/init init=/sbin/init') if installed else 'rdinit=/init init=/init ro panic=15 net.ifnames=0'
        subprocess.run([sys.executable,str(BASE/'assets/mkbootimg.py'),'--kernel',str(root/'boot'/('vmlinuz-'+KERNEL)),'--ramdisk',str(out/(kind+'.cpio.gz')),'--second',str(assets/'resource.img'),'--dtb',str(assets/'board.dtb'),'--recovery_dtbo',str(assets/'recovery_dtbo'),'--header_version','2','--pagesize','2048','--base','0x10000000','--kernel_offset','0x8000','--ramdisk_offset','0x01000000','--second_offset','0x00f00000','--tags_offset','0x100','--dtb_offset','0x01f00000','--os_version','12.0.0','--os_patch_level','2022-07','--cmdline',cmdline,'--output',str(out/(kind+'.img'))],check=True)
        return image_record(out/(kind+'.img'))
    recovery=pack('recovery');installed=pack('installed',True)
    # Keep private RAM assets for on-device kernel rebuilds. No host private key enters the public toolkit.
    maintenance=root/'usr/local/lib/lincstation';shutil.copytree(assets,maintenance)
    for name in ['mkbootimg.py','gki']:
        src=BASE/'assets'/name
        if src.is_dir():shutil.copytree(src,maintenance/name)
        else:shutil.copy2(src,maintenance/name)
    shutil.copy2(ram/'init',maintenance/'init');(maintenance/'init').chmod(0o755)
    subprocess.run(['tar','--numeric-owner','--exclude=./lib/modules','--exclude=./www/*','-czf',str(maintenance/'initramfs-base.tar.gz'),'-C',str(ram),'.'],check=True)
    record={'kernel':KERNEL,'recovery':recovery,'installed':installed,'emmc_cid':plan['emmc_cid'],'root_uuid':plan['root_uuid']}
    save(maintenance/'boot-manifest.json',record);maintenance.chmod(0o700)
    put('usr/local/sbin/lincstation-update-kernel',(BASE/'templates/lincstation-update-kernel').read_text(),0o755)
    shutil.copy2(BASE/'e1lib.py',root/'usr/local/sbin/e1lib.py')
    shutil.copy2(BASE/'enable-kernel-hook.py',root/'usr/local/sbin/lincstation-enable-kernel-hook')
    (root/'usr/local/sbin/lincstation-enable-kernel-hook').chmod(0o755)
    put('usr/local/lib/lincstation/kernel-hook.pending','#!/bin/sh\nset -eu\n[ -n "${1:-}" ] || exit 0\nexec /usr/local/sbin/lincstation-update-kernel --install "$1"\n',0o755)
    (root/'usr/sbin/policy-rc.d').unlink();chroot('apt-get','clean');put('etc/machine-id','')
    if not (root/'etc/resolv.conf').is_symlink():put('etc/resolv.conf','nameserver '+plan['dns']+'\n')
    for f in (root/'var/log').rglob('*'):
        if f.is_file() and not f.is_symlink():f.write_bytes(b'')
    for mode,dir_,port in [('installed',root,22),('recovery',ram,2223)]:
        key=' '.join((dir_/'etc/ssh/ssh_host_ed25519_key.pub').read_text().split()[:2]);host=plan['nas_ip'] if port==22 else '['+plan['nas_ip']+']:'+str(port)
        (work/(mode+'-known_hosts')).write_text(host+' '+key+'\n')
    archive=out/'rootfs.tar.gz';subprocess.run(['tar','--numeric-owner','--acls','--xattrs','-czf',str(archive),'-C',str(root),'.'],check=True)
    record['rootfs']={'sha256':sha(archive),'bytes':archive.stat().st_size};save(out/'manifest.json',record)
    # Publish only transport artifacts to the helper user; keep rootfs ownership intact.
    owner=work.stat()
    for f in [out,out/'manifest.json',out/'recovery.img',out/'installed.img',archive,work/'installed-known_hosts',work/'recovery-known_hosts']:
        os.chown(f,owner.st_uid,owner.st_gid)
    print(json.dumps(record,indent=2));print('Build complete. No NAS partitions were written.')
if __name__=='__main__':build(Path(sys.argv[1]).resolve())
