#!/usr/bin/env python3
"""Staged E1 migration. Run on a macOS or Debian 13 (ARM64/x86-64) helper, not on the NAS."""
import argparse,fcntl,gzip,hashlib,ipaddress,json,os,re,shlex,shutil,socket,subprocess,sys,threading,time,uuid
from pathlib import Path
from e1lib import *
BASE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work',type=Path,required=True,help='Private state directory OUTSIDE the shareable toolkit')
    sub=p.add_subparsers(dest='command',required=True)
    def software_flags(q):
        q.add_argument('--desktop',action=argparse.BooleanOptionalAction,help='Install the LXDE desktop (--no-desktop for a headless NAS)')
        q.add_argument('--apps',metavar='LIST',help='Desktop app groups: comma-separated '+', '.join(APP_GROUPS)+', or all/none')
        q.add_argument('--vnc',action=argparse.BooleanOptionalAction,help='Install tunneled VNC for the desktop')
    q=sub.add_parser('init');q.add_argument('--nas',required=True,help='Reserved static IPv4 address/prefix, e.g. 192.168.1.50/24');q.add_argument('--gateway',required=True);q.add_argument('--dns');q.add_argument('--timezone',default='Etc/UTC');q.add_argument('--user',default='nas');q.add_argument('--adb-serial',help='Default NAS_IP:5555')
    software_flags(q)
    for name in ('root','probe','backup','build','status','verify-a','verify-b','verify-debian','verify-stock'):sub.add_parser(name)
    software_flags(sub.add_parser('finish',help='Install OMV and the chosen extras; software flags override the choices made at init'))
    for name in ('stage-a','return-stock','stage-b','install'):
        q=sub.add_parser(name);q.add_argument('--write',action='store_true',help='Permit the named boot-partition/metadata operation')
        if name=='install':q.add_argument('--erase-emmc-userdata',metavar='CID',required=True)
    q=sub.add_parser('reboot');q.add_argument('--from',dest='source',choices=['stock','recovery','installed'],required=True)
    q.add_argument('--timeout',type=int,default=300,help='Seconds to wait before asking for a power cycle (default 300)');q.add_argument('--no-wait',action='store_true',help='Return immediately after requesting the reboot')
    a=p.parse_args();work=a.work.expanduser().resolve()
    def software(current,prompt):
        flags=getattr(a,'desktop',None),getattr(a,'apps',None),getattr(a,'vnc',None)
        if flags==(None,None,None):return choose_software(current) if prompt and sys.stdin.isatty() else software_options(**current)
        desktop=current['desktop'] if a.desktop is None else a.desktop
        if not desktop and (a.apps or a.vnc):print('No desktop selected; ignoring app groups and VNC.')
        return software_options(desktop,current['apps'] if a.apps is None else parse_apps(a.apps),current['vnc'] if a.vnc is None else a.vnc)
    require(BASE!=work and BASE not in work.parents,'Keep private work outside the shareable toolkit')
    os.umask(0o077)
    if a.command=='init':
        require(not work.exists(),'Choose a new work directory')
        network=ipaddress.IPv4Interface(a.nas);gateway=ipaddress.IPv4Address(a.gateway);dns=ipaddress.IPv4Address(a.dns or a.gateway)
        require(gateway in network.network,'Gateway must be in the NAS subnet')
        require(re.fullmatch('[a-z_][a-z0-9_-]*',a.user) and a.user not in ('root','sshd','nobody'),'Choose a normal user name')
        require(not a.timezone.startswith('/') and Path('/usr/share/zoneinfo',a.timezone).is_file() and '..' not in a.timezone,'Unknown timezone')
        sw=software(DEFAULT_SOFTWARE,prompt=True)
        work.mkdir(mode=0o700,parents=True)
        save(work/'config.json',dict(nas_ip=str(network.ip),prefix=network.network.prefixlen,gateway=str(gateway),dns=str(dns),timezone=a.timezone,user=a.user,adb_serial=a.adb_serial or str(network.ip)+':5555',run_id=uuid.uuid4().hex[:12],software=sw))
        print('Extras: '+(', '.join(['desktop']+sw['apps']+(['vnc'] if sw['vnc'] else [])) if sw['desktop'] else 'none (headless OMV)')+'. Change them later with finish --desktop/--no-desktop, --apps and --vnc/--no-vnc.')
        subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(work/'owner-key')],check=True)
        print('Created private work directory and a fresh migration SSH key. Keep this directory private.');return
    require((work/'config.json').is_file(),'Run init first')
    lock=(work/'operation.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    config=json.loads((work/'config.json').read_text())
    def ssh(mode):
        port=22222 if mode=='stock' else 2223 if mode=='recovery' else 22
        host='127.0.0.1' if mode=='stock' else config['nas_ip']
        return ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=15','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(work/(mode+'-known_hosts')),'-i',str(work/'owner-key'),'-p',str(port),'root@'+host]
    def remote(mode,command,**kw):return subprocess.run(ssh(mode)+[command],check=True,**kw)
    def send(mode,local,dest):
        with open(local,'rb') as f:remote(mode,'cat > '+shlex.quote(dest),stdin=f)
    def device(mode,request):
        for name in ('e1lib.py','device.py'):send(mode,BASE/name,'/tmp/'+name)
        result=remote(mode,'python3 /tmp/device.py',input=json.dumps(request),capture_output=True,text=True)
        lines=result.stdout.splitlines()
        for line in lines[:-1]:print(line,flush=True)
        return json.loads(lines[-1])
    def plan():return json.loads((work/'plan.json').read_text())
    def manifest():return json.loads((work/'build/manifest.json').read_text())
    def backup_guard():
        b=json.loads((work/'backup/manifest.json').read_text());require(b['emmc_cid']==plan()['emmc_cid'] and b['full']['verified'],'Backup does not match this device')
        require(sha(work/'backup/emmc-full-live.img.gz')==b['full']['compressed_sha256'],'Full backup changed')
        for name,expected in STOCK.items():require(sha(work/'backup'/name)==expected,'Unsupported or damaged stock '+name)
    if a.command=='root':
        subprocess.run([sys.executable,str(BASE/'root-stock.py'),str(work)],check=True)
        probe=device('stock',{'action':'probe'})
        require(probe['stock'] and 'androidboot.slot_suffix=_b' in probe['cmdline'] and probe['slot_b'][2]==1,'Supported start is successful stock slot B; do not force an untested slot')
        if (work/'plan.json').exists():require(plan()['emmc_cid']==probe['emmc_cid'],'This work directory belongs to another NAS')
        else:
            require(re.fullmatch('[0-9a-f]{32}',probe['emmc_cid']),'Unexpected CID')
            require(re.fullmatch('(?:[0-9a-f]{2}:){5}[0-9a-f]{2}',probe['factory_mac']),'Unexpected MAC')
            save(work/'plan.json',dict(config,emmc_cid=probe['emmc_cid'],factory_mac=probe['factory_mac'],root_uuid=str(uuid.uuid4()),root_partition_partuuid=ROOT_PARTUUID,root_partition_size=ROOT_SIZE,root_partition_number=19,root_label='debian-root'))
        save(work/'stock-probe.json',probe);print(json.dumps(probe,indent=2))
    elif a.command=='probe':print(json.dumps(device('stock',{'action':'probe'}),indent=2))
    elif a.command=='backup':
        require(shutil.disk_usage(work).free>=80*1024**3,'At least 80 GiB free required for conservative full-backup capacity')
        probe=device('stock',{'action':'probe'});require(probe['emmc_cid']==plan()['emmc_cid'] and probe['stock'],'Unexpected device')
        dest=work/'backup';dest.mkdir(exist_ok=True);require(not (dest/'manifest.json').exists(),'Backup already completed; do not overwrite')
        records={}
        parts=['security','uboot_a','uboot_b','trust_a','trust_b','misc','dtbo_a','dtbo_b','vbmeta_a','vbmeta_b','boot_a','boot_b','backup','baseparameter','mmcblk2boot0','mmcblk2boot1']
        for name in parts:
            dev='/dev/block/by-name/'+name;target=dest/(name+'.img');require(not target.exists(),'Partial backup exists: inspect and move it before retrying')
            size=int(remote('stock','blockdev --getsize64 '+dev,capture_output=True,text=True).stdout);require(0<size<=512*1024*1024,'Unexpected critical partition size')
            with target.open('xb') as f:remote('stock','dd if='+dev+' bs=4M status=none',stdout=f)
            digest=remote('stock','sha256sum '+dev,capture_output=True,text=True).stdout.split()[0]
            require(target.stat().st_size==size and sha(target)==digest,'Critical backup mismatch: '+name)
            records[target.name]={'sha256':digest,'bytes':size};print('Backed up and verified '+name,flush=True)
        for name,expected in STOCK.items():require(records[name]['sha256']==expected,'Unsupported stock firmware; stopped before any partition write')
        remote('stock','sfdisk --dump /dev/block/mmcblk2',stdout=(dest/'partition-table.txt').open('w'))
        # Compress on the NAS while hashing the exact uncompressed stream. Re-read the stored gzip locally.
        code="""import gzip,hashlib,json,sys
h=hashlib.sha256();n=0
with open('/dev/block/mmcblk2','rb') as f,gzip.GzipFile(fileobj=sys.stdout.buffer,mode='wb',compresslevel=1,mtime=0) as z:
 while True:
  b=f.read(4194304)
  if not b:break
  z.write(b);h.update(b);n+=len(b)
print(json.dumps({'bytes':n,'sha256':h.hexdigest()}),file=sys.stderr)
"""
        partial=dest/'emmc-full-live.img.gz.partial';require(not partial.exists(),'Partial full backup exists')
        print('Streaming full eMMC backup; this can take tens of minutes.',flush=True)
        with partial.open('xb') as f:
            proc=subprocess.Popen(ssh('stock')+['python3 -c '+shlex.quote(code)],stdout=f,stderr=subprocess.PIPE)
            while proc.poll() is None:
                try:proc.wait(timeout=30)
                except subprocess.TimeoutExpired:print('Compressed backup bytes:',partial.stat().st_size,flush=True)
            stderr=proc.stderr.read();require(proc.returncode==0,'Backup stream failed: '+stderr.decode(errors='replace'));f.flush();os.fsync(f.fileno())
        source=json.loads(stderr.decode().splitlines()[-1]);h=hashlib.sha256();n=0
        with gzip.open(partial,'rb') as f:
            while b:=f.read(8388608):h.update(b);n+=len(b)
        require(n==EMMC_SIZE==source['bytes'] and h.hexdigest()==source['sha256'],'Full backup verification failed')
        final=dest/'emmc-full-live.img.gz';partial.rename(final)
        save(dest/'manifest.json',dict(emmc_cid=plan()['emmc_cid'],critical=records,full=dict(verified=True,raw_bytes=n,raw_sha256=h.hexdigest(),compressed_sha256=sha(final)),note='Live mounted stock eMMC, not an offline filesystem-consistent snapshot'))
        print('Full backup stored and decompression/hash verified.')
    elif a.command=='build':
        backup_guard()
        if sys.platform=='darwin':container_build(work)
        else:subprocess.run(['sudo',sys.executable,str(BASE/'build.py'),str(work)],check=True)
    elif a.command in ('stage-a','stage-b','install','return-stock'):
        require(a.write,'No write performed. Review the README, then repeat this explicit stage with --write.')
        backup_guard();mode='stock' if a.command=='stage-a' else 'recovery';request=dict(action=a.command,plan=plan(),manifest=manifest(),backup=json.loads((work/'backup/manifest.json').read_text()))
        if a.command=='stage-b':
            require((work/'verified-a.json').is_file() and (work/'verified-stock-roundtrip.json').is_file(),'Verify RAM A and its normal reboot to stock before replacing B')
        if a.command=='install':
            require((work/'verified-b.json').is_file(),'Verify recovery B boot first')
            request.update(erase_cid=a.erase_emmc_userdata,epoch=int(time.time()))
            require(a.erase_emmc_userdata==plan()['emmc_cid'],'Erase CID does not match')
            for name,dest in [('rootfs.tar.gz','/tmp/e1-rootfs.tar.gz'),('installed.img','/tmp/e1-installed.img')]:send(mode,work/'build'/name,dest)
        elif a.command in ('stage-a','stage-b'):send(mode,work/'build/recovery.img','/tmp/e1-recovery.img')
        if a.command in ('stage-b','install'):
            current=device(mode,{'action':'probe'});proof=json.loads((work/('verified-a.json' if a.command=='stage-b' else 'verified-b.json')).read_text())
            require(current['boot_id']==proof['boot_id'],'Boot changed since verification; run the appropriate verify command again')
        result=device(mode,request);save(work/('staged-'+a.command+'.json'),result);print(json.dumps(result,indent=2));print('No automatic reboot. Use the explicit reboot command next.')
    elif a.command=='reboot':
        mode=a.source;probe=device(mode,{'action':'probe'});require(probe['emmc_cid']==plan()['emmc_cid'],'Wrong NAS')
        save(work/'last-reboot.json',dict(previous_boot_id=probe['boot_id'],source=mode,time=int(time.time())))
        cmd='chroot /proc/1/root /system/bin/reboot' if mode=='stock' else '/bin/busybox reboot -f' if mode=='recovery' else 'systemctl reboot'
        result=subprocess.run(ssh(mode)+[cmd]);require(result.returncode in (0,255),'Reboot command failed')
        if a.no_wait:print('Reboot requested. Run the matching verify command once the NAS is back.')
        else:wait_after_reboot(work,config['nas_ip'],mode,a.timeout)
    elif a.command=='verify-stock':
        old=json.loads((work/'staged-return-stock.json').read_text())['previous_boot_id'];current=device('stock',{'action':'probe'})
        require(current['boot_id']!=old and current['emmc_cid']==plan()['emmc_cid'] and current['stock'] and 'androidboot.slot_suffix=_b' in current['cmdline'],'Stock roundtrip not verified')
        save(work/'verified-stock-roundtrip.json',current);print('Normal recovery-A to stock-B roundtrip verified.')
    elif a.command.startswith('verify-'):
        mode='installed' if a.command=='verify-debian' else 'recovery';slot='b' if a.command=='verify-b' else 'a'
        previous=json.loads((work/'last-reboot.json').read_text())['previous_boot_id']
        result=device(mode,dict(action='verify',plan=plan(),mode=mode,slot=slot,previous_boot_id=previous))
        save(work/('verified-'+('debian' if mode=='installed' else slot)+'.json'),result);print(json.dumps(result,indent=2))
    elif a.command=='finish':
        require((work/'verified-debian.json').is_file(),'Verify installed Debian boot first')
        sw=software(config.get('software',DEFAULT_SOFTWARE),prompt=False)
        if sw!=config.get('software'):config['software']=sw;save(work/'config.json',config)
        subprocess.run([sys.executable,str(BASE/'finish.py'),str(work),json.dumps(sw)],check=True)
    elif a.command=='status':
        for name in sorted(work.glob('*.json')):
            if name.name!='credentials.json':print(name.name+': '+name.read_text())
# Each environment answers on its own port: RAM recovery SSH, stock ADB / LincOS web UI, installed Debian SSH.
ENVIRONMENTS=[(2223,'recovery','RAM recovery'),(5555,'stock','stock Android'),(50080,'stock','stock Android'),(22,'installed','installed Debian')]
NEXT={'recovery':'verify-a (or verify-b if you just ran stage-b)','stock':'root (to reopen root SSH; re-enable Wireless debugging on the NAS first if adb cannot connect), then verify-stock','installed':'verify-debian'}
EXPECTED={'stage-a':('recovery','verify-a'),'return-stock':('stock','root (re-enable Wireless debugging on the NAS first if adb cannot connect), then verify-stock'),'stage-b':('recovery','verify-b'),'install':('installed','verify-debian')}
def detect(ip):
    for port,mode,label in ENVIRONMENTS:
        try:socket.create_connection((ip,port),timeout=2).close();return mode,label
        except OSError:pass
def wait_after_reboot(work,ip,source,timeout):
    staged=sorted(work.glob('staged-*.json'),key=lambda f:f.stat().st_mtime)
    expected=EXPECTED.get(staged[-1].stem[7:]) if staged else None
    # Let the old environment shut down first, so it isn't mistaken for the new one.
    print('Reboot requested. Waiting for the NAS to shut down...',flush=True);time.sleep(15)
    gone=time.time()+60
    while time.time()<gone and (old:=detect(ip)) and old[0]==source:time.sleep(3)
    while True:
        print(f'Waiting up to {timeout//60} minutes for the NAS to come back...',flush=True)
        deadline=time.time()+timeout;note=time.time()+30
        while time.time()<deadline:
            found=detect(ip)
            if found:
                mode,label=found;print('The NAS is back in '+label+'.')
                if expected and mode!=expected[0]:
                    print('Note: this stage expected '+dict((m,l) for _,m,l in ENVIRONMENTS)[expected[0]]+'. The bootloader fell back to the other slot, which is the safety net working. Nothing was lost; check the stage output before retrying.')
                print('Next: python3 e1-migrate.py --work "'+str(work)+'" '+(expected[1] if expected and mode==expected[0] else NEXT[mode]));return
            if time.time()>=note:print(f'  still waiting ({int(deadline-time.time())}s left)',flush=True);note+=30
            time.sleep(5)
        print('''
  ========================================================================
   The NAS hasn't come back. The E1 sometimes hangs on a software restart.

   1. Unplug the NAS's power cable. The front button does NOT fully
      cut power.
   2. Wait 10 seconds.
   3. Plug it back in and switch it on.

   A power cycle is safe at every stage: the bootloader starts either
   the new boot slot or the known-good slot B, and this tool will tell
   you which one came back.
  ========================================================================''')
        if not sys.stdin.isatty():raise SystemExit('Power-cycle the NAS, then run the matching verify command.')
        input('Press Enter once the NAS is plugged back in and switched on... ')
def container_build(work):
    """macOS helper: build.py needs Linux, so run it in a throwaway privileged Debian 13 ARM64 container.
    Only the public key, plan and three stock boot images go in; only the transport artifacts come out."""
    require(shutil.which('docker'),'Building on macOS needs Docker Desktop, OrbStack or Colima')
    require(subprocess.run(['docker','info'],capture_output=True).returncode==0,'Start Docker (or OrbStack/Colima) before building')
    out=work/'build';require(not out.exists(),'Build directory exists; preserve it and choose a fresh work build directory before retrying')
    stage=work/'container-build';require(not stage.exists(),'Leftover container-build directory; inspect and remove it before retrying')
    (stage/'in/backup').mkdir(parents=True);(stage/'out').mkdir()
    for name in ('plan.json','owner-key.pub'):shutil.copy2(work/name,stage/'in'/name)
    for name in STOCK:shutil.copy2(work/'backup'/name,stage/'in/backup'/name)
    # The build root stays on the container's own Linux filesystem: macOS file sharing cannot hold its ownership, device nodes or xattrs.
    script=('set -eu; apt-get update -qq; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends python3 >/dev/null; '
        'mkdir -m 700 /work; cp -a /stage/in/. /work/; python3 /toolkit/build.py /work; '
        'cp /work/build/manifest.json /work/build/recovery.img /work/build/installed.img /work/build/rootfs.tar.gz /work/installed-known_hosts /work/recovery-known_hosts /stage/out/')
    print('macOS helper: building inside a temporary Debian 13 ARM64 container.',flush=True)
    subprocess.run(['docker','run','--rm','--privileged','--platform','linux/arm64','-v',str(BASE)+':/toolkit:ro','-v',str(stage)+':/stage','debian:trixie','sh','-c',script],check=True)
    record=json.loads((stage/'out/manifest.json').read_text())
    for name,expected in (('recovery.img',record['recovery']),('installed.img',record['installed'])):require(image_record(stage/'out'/name)==expected,'Copied '+name+' does not match the build manifest')
    require(sha(stage/'out/rootfs.tar.gz')==record['rootfs']['sha256'],'Copied rootfs.tar.gz does not match the build manifest')
    out.mkdir(mode=0o700)
    for name in ('manifest.json','recovery.img','installed.img','rootfs.tar.gz'):(stage/'out'/name).rename(out/name)
    for name in ('installed-known_hosts','recovery-known_hosts'):(stage/'out'/name).rename(work/name)
    shutil.rmtree(stage);print('Build artifacts verified and copied into '+str(out)+'. No NAS partitions were written.')
if __name__=='__main__':main()
