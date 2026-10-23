#!/usr/bin/env python3
"""Install OMV first, then a normal console user and the selected extras: LXDE, app groups and tunneled VNC."""
import json,os,pwd,shutil,subprocess,sys
from pathlib import Path
from e1lib import require,run,software_options,DEFAULT_SOFTWARE
BASE=Path(__file__).resolve().parent

def main():
    require(os.geteuid()==0,'Root required');plan=json.loads(Path('/etc/lincstation-install.json').read_text());creds=json.load(sys.stdin)
    require(run('findmnt','-n','-o','UUID','/')==plan['root_uuid'],'Wrong root filesystem')
    require(Path('/sys/block/mmcblk0/device/cid').read_text().strip()==plan['emmc_cid'],'Wrong eMMC')
    env=dict(os.environ,DEBIAN_FRONTEND= 'noninteractive',LANG='C.UTF-8',APT_LISTCHANGES_FRONTEND='none')
    def cmd(*args,**kw):return subprocess.run(args,check=True,env=env,**kw)
    cmd('systemctl','enable','--now','systemd-resolved.service');cmd('resolvectl','dns','eth0',plan['dns'])
    if subprocess.run(['dpkg-query','-W','-f=${db:Status-Status}','openmediavault'],capture_output=True,text=True).stdout.strip()!='installed':
        cmd('apt-get','update');cmd('apt-get','-y','--no-install-recommends','install','gnupg','curl','psmisc')
        cmd('curl','-fsSL','https://packages.openmediavault.io/archive.key','-o','/tmp/e1-omv-archive.key')
        cmd('gpg','--dearmor','--yes','--output','/usr/share/keyrings/openmediavault-archive-keyring.gpg','/tmp/e1-omv-archive.key')
        Path('/etc/apt/sources.list.d/openmediavault.list').write_text('deb [signed-by=/usr/share/keyrings/openmediavault-archive-keyring.gpg] https://packages.openmediavault.io/ synchrony main\n')
        cmd('apt-get','update');cmd('apt-get','-y','--no-install-recommends','--option','DPkg::Options::=--force-confdef','--option','DPkg::Options::=--force-confold','install','openmediavault')
        cmd('omv-confdbadm','populate')
    def read(model):return json.loads(run('omv-confdbadm','read',model))
    def update(model,value):cmd('omv-confdbadm','update',model,'-',input=json.dumps(value),text=True)
    networks=read('conf.system.network.interface');matches=[n for n in networks if n['devicename']=='eth0']
    require(len(matches)==1 and matches[0]['address']==plan['nas_ip'],'OMV did not import expected static eth0; use omv-firstaid before continuing')
    net=matches[0];net['altmacaddress']=plan['factory_mac'];update('conf.system.network.interface',net)
    ssh=read('conf.service.ssh');ssh.update(enable=True,passwordauthentication=False,permitrootlogin=True,pubkeyauthentication=True);update('conf.service.ssh',ssh)
    tm=read('conf.system.time');tm['timezone']=plan['timezone'];update('conf.system.time',tm)
    user=plan['user']
    try:u=pwd.getpwnam(user)
    except KeyError:cmd('useradd','--create-home','--shell','/bin/bash',user);u=pwd.getpwnam(user)
    require(u.pw_uid>=1000,'Expected normal console user')
    cmd('usermod','-aG','sudo,audio,video,render,_ssh',user)
    home=Path(u.pw_dir);keys=home/'.ssh';keys.mkdir(mode=0o700,exist_ok=True);keys.chmod(0o700);os.chown(keys,u.pw_uid,u.pw_gid)
    auth=keys/'authorized_keys';auth.write_bytes(Path('/root/.ssh/authorized_keys').read_bytes());auth.chmod(0o600);os.chown(auth,u.pw_uid,u.pw_gid)
    cmd('chpasswd',input=user+':'+creds['console']+'\n',text=True)
    import openmediavault.rpc
    openmediavault.rpc.call('UserMgmt','setPasswordByContext',{'password':creds['admin']})
    cmd('omv-salt','deploy','run','systemd-networkd','ssh','timezone')
    old=Path('/etc/systemd/network/80-lincstation.network')
    if old.exists():old.rename('/usr/local/lib/lincstation/original-static.network')
    cmd('networkctl','reload');cmd('networkctl','reconfigure','eth0')
    sw=software_options(**creds.get('software',DEFAULT_SOFTWARE))
    if sw['desktop']:cmd('sh',str(BASE/'install-desktop.sh'),user,'--apps',','.join(sw['apps']) or 'none')
    if sw['vnc']:cmd('python3',str(BASE/'setup-vnc.py'),user,'--password-stdin',input=creds['vnc']+'\n',text=True)
    guide=Path('/usr/local/share/doc/lincstation/README.md')
    if guide.is_file():
        copy=home/'LINCSTATION-README.md';shutil.copy2(guide,copy);copy.chmod(0o644);os.chown(copy,u.pw_uid,u.pw_gid)
    cmd('systemctl','is-active','--quiet','ssh','nginx','openmediavault-engined','lincstation-boot-success')
    require(not run('dpkg','--audit'),'Package audit requires attention')
    extras=(['LXDE']+sw['apps'] if sw['desktop'] else [])+(['VNC'] if sw['vnc'] else [])
    print('OMV and console user installed'+('; extras: '+', '.join(extras)+'. Run startx locally to start the desktop.' if extras else '; no desktop (headless).'))
if __name__=='__main__':main()
