#!/usr/bin/env python3
"""Share an existing user's HDMI/X11 desktop through an SSH tunnel (Debian 13)."""
import argparse, getpass, os, pwd, re, shutil, subprocess, sys
from pathlib import Path

def run(args, **kw):
    return subprocess.run(args, check=True, **kw)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('user'); p.add_argument('--password-stdin', action='store_true')
    p.add_argument('--live', action='store_true')
    a=p.parse_args()
    if os.geteuid()!=0: p.error('Run as root')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*', a.user): p.error('Invalid user name')
    u=pwd.getpwnam(a.user); home=Path(u.pw_dir)
    if u.pw_uid<1000 or not home.is_dir(): p.error('Select an existing normal user')
    conf=Path('/etc/ssh/sshd_config')
    if not re.search(r'^Include\s+/etc/ssh/sshd_config.d/\*\.conf\s*$', conf.read_text(), re.M):
        p.error('sshd_config must include /etc/ssh/sshd_config.d/*.conf; no SSH changes made')
    password=sys.stdin.readline().rstrip('\n') if a.password_stdin else getpass.getpass('VNC password (exactly 8 printable ASCII characters): ')
    if len(password)!=8 or not all(33<=ord(c)<=126 for c in password): p.error('Choose exactly 8 printable ASCII characters, without spaces')
    if not a.password_stdin and password!=getpass.getpass('Repeat VNC password: '): p.error('Passwords differ')
    env=dict(os.environ, DEBIAN_FRONTEND='noninteractive')
    run(['apt-get','update'], env=env)
    packages=['x11vnc','util-linux']
    plan=run(['apt-get','-s','--no-install-recommends','install',*packages],capture_output=True,text=True,env=env).stdout
    if re.search(r'^Remv ',plan,re.M): raise SystemExit('APT would remove packages; stopped')
    run(['apt-get','-y','--no-install-recommends','install',*packages],env=env)
    vnc=home/'.vnc'; vnc.mkdir(mode=0o700,exist_ok=True);vnc.chmod(0o700);os.chown(vnc,u.pw_uid,u.pw_gid)
    # x11vnc's interactive input avoids placing the password in process arguments.
    result=subprocess.run(['runuser','-u',a.user,'--','x11vnc','-storepasswd',str(vnc/'passwd')],input=password+'\n'+password+'\ny\n',text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
    password=None
    if result.returncode or not (vnc/'passwd').is_file() or (vnc/'passwd').stat().st_size!=8:
        raise SystemExit('Password creation failed; rerun x11vnc -storepasswd as the desktop user')
    (vnc/'passwd').chmod(0o600)
    wrapper=Path('/usr/local/bin/lincstation-vnc')
    wrapper.write_text('''#!/bin/sh
set -eu
[ -n "${DISPLAY:-}" ] || exit 0
[ -r "$HOME/.vnc/passwd" ] || exit 0
umask 077
mkdir -p "$HOME/.local/state/lincstation-vnc"
exec 9>"$HOME/.local/state/lincstation-vnc/lock"
flock -n 9 || exit 0
exec x11vnc -localhost -forever -shared -rfbport 5900 \
    -rfbauth "$HOME/.vnc/passwd" -display "$DISPLAY" \
    -auth "${XAUTHORITY:-$HOME/.Xauthority}" -noxdamage \
    -o "$HOME/.local/state/lincstation-vnc/server.log"
''');wrapper.chmod(0o755)
    # XDG autostart is independent of the LXDE panel configuration and survives reruns.
    folder=home/'.config/autostart'
    created=[]; parent=folder
    while not parent.exists(): created.append(parent);parent=parent.parent
    folder.mkdir(parents=True,exist_ok=True)
    for parent in created: os.chown(parent,u.pw_uid,u.pw_gid)
    desktop=folder/'lincstation-vnc.desktop'
    desktop.write_text('[Desktop Entry]\nType=Application\nName=HDMI Desktop Sharing\nExec=/usr/local/bin/lincstation-vnc\nOnlyShowIn=LXDE;\nTerminal=false\n');os.chown(desktop,u.pw_uid,u.pw_gid)
    drop=Path('/etc/ssh/sshd_config.d/60-lincstation-vnc-'+a.user+'.conf')
    old=drop.read_bytes() if drop.exists() else None
    drop.write_text('Match User '+a.user+'\n    AllowTcpForwarding local\n    PermitOpen 127.0.0.1:5900\nMatch all\n')
    try:
        run(['/usr/sbin/sshd','-t'])
        effective=run(['/usr/sbin/sshd','-T','-C','user='+a.user+',host=localhost,addr=127.0.0.1'],capture_output=True,text=True).stdout
        if 'allowtcpforwarding local\n' not in effective or 'permitopen 127.0.0.1:5900\n' not in effective:
            raise RuntimeError('Existing SSH configuration overrides the tunnel restriction')
        run(['systemctl','reload','ssh'])
    except Exception:
        if old is None: drop.unlink()
        else: drop.write_bytes(old)
        raise
    if a.live:
        ids=run(['pgrep','-u',str(u.pw_uid),'-x','openbox'],capture_output=True,text=True).stdout.split()
        if len(ids)!=1: raise SystemExit('VNC configured for next startx; live start needs one Openbox session')
        pairs=Path('/proc/'+ids[0]+'/environ').read_bytes().decode().split('\0')
        source=dict(s.split('=',1) for s in pairs if '=' in s)
        variables={k:source[k] for k in ['DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS','XDG_RUNTIME_DIR'] if k in source}
        variables['HOME']=str(home)
        subprocess.Popen(['runuser','-u',a.user,'--','env',*[k+'='+v for k,v in variables.items()],str(wrapper)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    print('VNC configured on loopback port 5900; starts with LXDE. Use SSH local forwarding to 127.0.0.1:5900.')
if __name__=='__main__': main()
