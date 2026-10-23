#!/usr/bin/env python3
"""Internal remote helper. Writes only the fixed E1 partition targets after guards."""
import fcntl,json,os,subprocess,sys,time
from pathlib import Path
from e1lib import *
def probe():
    stock=Path('/dev/block/mmcblk2').exists()
    dev='/dev/block/mmcblk2' if stock else '/dev/mmcblk0'
    sysdev='mmcblk2' if stock else 'mmcblk0'
    require(os.geteuid()==0,'Root required')
    require(int(run('blockdev','--getsize64',dev))==EMMC_SIZE,'Unsupported eMMC capacity')
    require(int(run('blockdev','--getsize64',dev+'p19'))==ROOT_SIZE,'Unsupported userdata capacity')
    require(run('blkid','-s','PARTUUID','-o','value',dev+'p19').lower()==ROOT_PARTUUID,'Unsupported partition layout')
    for n in (11,12):require(int(run('blockdev','--getsize64',dev+'p'+str(n)))==BOOT_SIZE,'Unsupported boot partition')
    with open(dev+'p6','rb') as f:f.seek(2048);a,b=read_ab(f.read(512))
    return dict(stock=stock,device=dev,emmc_cid=Path('/sys/block/'+sysdev+'/device/cid').read_text().strip(),factory_mac=Path('/sys/class/net/eth0/address').read_text().strip(),cmdline=Path('/proc/cmdline').read_text().strip(),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),slot_a=a,slot_b=b,root_source=run('findmnt','-n','-o','SOURCE','/') if not stock and Path('/usr/bin/findmnt').exists() else None)
def operate():
    request=json.load(sys.stdin);action=request['action'];p=probe()
    if action=='probe': print(json.dumps(p));return
    plan=request['plan'];require(p['emmc_cid']==plan['emmc_cid'],'eMMC identity mismatch')
    if action=='verify':
        mode=request['mode'];require(not p['stock'],'Expected Linux')
        require('androidboot.slot_suffix=_'+request['slot'] in p['cmdline'],'Wrong boot slot')
        require(p['boot_id']!=request['previous_boot_id'],'No new boot observed')
        require(Path('/sys/firmware/devicetree/base/compatible').read_bytes().startswith(b'techvision,tvd8322r\0'),'Wrong board DT')
        if mode=='installed':
            require(run('findmnt','-n','-o','UUID','/')==plan['root_uuid'],'Wrong root UUID')
            subprocess.run(['systemctl','is-active','--quiet','ssh','lincstation-boot-success'],check=True)
        else:
            require(Path('/etc/e1-recovery').read_text().strip()==plan['root_uuid'],'Not the expected RAM recovery')
            require(not any(x.split()[0].startswith('/dev/') for x in Path('/proc/mounts').read_text().splitlines()),'A disk is mounted in recovery')
        print(json.dumps(p));return
    manifest=request['manifest'];dev=p['device'];misc=dev+'p6';aa=dev+'p11';bb=dev+'p12';recovery=manifest['recovery'];image=manifest['installed']
    if action=='stage-a':
        require(p['stock'] and 'androidboot.slot_suffix=_b' in p['cmdline'],'Start from stock slot B')
        require(p['slot_b'][2]==1,'Stock B is not successful')
        require(sha(bb)==STOCK['boot_b.img'],'Unknown stock boot B')
        require(sha(dev+'p3')==STOCK['uboot_b.img'],'Unknown stock U-Boot B')
        require(sha(dev+'p8')==STOCK['dtbo_b.img'],'Unknown stock DTBO B')
        require(sha(aa) in (request['backup']['critical']['boot_a.img']['sha256'],recovery['padded_sha256']),'Boot A changed since backup')
        write_ab(misc,[0,0,0,0],[15,0,1,0]);write_image(aa,'/tmp/e1-recovery.img',recovery)
        write_ab(misc,[15,2,0,0],[14,0,1,0])
    else:
        require(not p['stock'],'Expected Linux recovery')
        require(Path('/etc/e1-recovery').read_text().strip()==plan['root_uuid'],'Not expected RAM recovery')
        require(not any(x.split()[0].startswith('/dev/') for x in Path('/proc/mounts').read_text().splitlines()),'Recovery must not have disks mounted')
        if action=='return-stock':
            require('androidboot.slot_suffix=_a' in p['cmdline'],'Expected RAM A')
            require(sha(bb)==STOCK['boot_b.img'],'Stock B changed')
            write_ab(misc,[0,0,0,0],[15,0,1,0])
        elif action=='stage-b':
            require('androidboot.slot_suffix=_a' in p['cmdline'],'Expected RAM A')
            require(sha(aa)==recovery['padded_sha256'],'Recovery A changed')
            require(sha(bb)==STOCK['boot_b.img'],'B is no longer original stock; stop for inspection')
            # The running, verified recovery A remains the fallback while B is written.
            write_ab(misc,[15,0,1,0],[0,0,0,0]);write_image(bb,'/tmp/e1-recovery.img',recovery)
            write_ab(misc,[14,0,1,0],[15,2,0,0])
        elif action=='install':
            require(request.get('erase_cid')==plan['emmc_cid'],'Explicit matching erase CID required')
            require('androidboot.slot_suffix=_b' in p['cmdline'],'Install only from RAM B')
            require(sha(aa)==recovery['padded_sha256'] and sha(bb)==recovery['padded_sha256'],'Both recovery slots must verify')
            require(sha('/tmp/e1-rootfs.tar.gz')==manifest['rootfs']['sha256'],'Root archive mismatch')
            require(sha('/tmp/e1-installed.img')==image['sha256'],'Installed image mismatch')
            rootdev=dev+'p19';write_ab(misc,[14,0,1,0],[15,0,1,0])
            subprocess.run(['date','-u','-s','@'+str(request['epoch'])],check=True)
            subprocess.run(['mkfs.ext4','-F','-m','1','-L','debian-root','-U',plan['root_uuid'],rootdev],check=True)
            mount=Path('/mnt/debian');mount.mkdir(exist_ok=True)
            subprocess.run(['mount','-t','ext4',rootdev,str(mount)],check=True)
            try:
                subprocess.run(['tar','--numeric-owner','--acls','--xattrs','-xzf','/tmp/e1-rootfs.tar.gz','-C',str(mount)],check=True)
                require(json.loads((mount/'etc/lincstation-install.json').read_text())==plan,'Wrong extracted plan')
                require((mount/'usr/lib/systemd/systemd').is_file(),'Missing systemd')
                require((mount/'root/.ssh/authorized_keys').stat().st_size>40,'Missing authorized key')
                require(run('blkid','-s','UUID','-o','value',rootdev)==plan['root_uuid'],'Root UUID mismatch');os.sync()
            finally:subprocess.run(['umount',str(mount)],check=True)
            subprocess.run(['e2fsck','-fn',rootdev],check=True)
            write_image(aa,'/tmp/e1-installed.img',image)
            require(sha(bb)==recovery['padded_sha256'],'Recovery B changed')
            write_ab(misc,[15,2,0,0],[14,0,1,0])
        else:raise RuntimeError('Unknown action')
    os.sync();print(json.dumps({'action':action,'complete':True,'previous_boot_id':p['boot_id'],'reboot_required':True}))
def main():
    with open('/tmp/e1-partition-operation.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        operate()
if __name__=='__main__':main()
