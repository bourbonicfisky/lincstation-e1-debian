#!/usr/bin/env python3
"""Configure an existing user; optional live panel/desktop update preserves open apps."""
import argparse, os, pwd, re, shutil, subprocess, time
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('user');p.add_argument('--live',action='store_true');a=p.parse_args()
assert os.geteuid()==0, 'Run as root'
u=pwd.getpwnam(a.user);home=Path(u.pw_dir)
assert u.pw_uid>=1000 and home.is_dir(), 'Select an existing normal user'
stamp=time.strftime('%Y%m%d-%H%M%S')
backup=home/'.local/state/lincstation-desktop/backups'/stamp
def own_parents(path):
    missing=[]
    while path!=home and not path.exists(): missing.append(path);path=path.parent
    for d in reversed(missing): d.mkdir();os.chown(d,u.pw_uid,u.pw_gid)
def put(rel,data,mode=0o644):
    if rel.endswith('/panels/panel'):
        data=re.sub(r'\{ ([^{}]*) \}',lambda m:'{\n '+m.group(1)+'\n}',data)
    f=home/rel
    if f.exists() and f.read_text()!=data:
        old=backup/rel;own_parents(old.parent);shutil.copy2(f,old);os.chown(old,u.pw_uid,u.pw_gid)
    own_parents(f.parent);f.write_text(data);f.chmod(mode);os.chown(f,u.pw_uid,u.pw_gid)
def mkdir(rel):
    d=home/rel;own_parents(d)
def has(entry):return Path('/usr/share/applications',entry).exists()
firefox,vlc,mousepad,scrot=has('firefox-esr.desktop'),has('vlc.desktop'),has('org.xfce.mousepad.desktop'),bool(shutil.which('scrot'))
for d in ['Desktop','Downloads','Videos','.config/lxpanel/LXDE/panels','.config/lxsession/LXDE','.config/pcmanfm/LXDE','.config/openbox','.config/gtk-3.0','.local/share/applications']:mkdir(d)
put('.xinitrc','#!/bin/sh\nexec dbus-run-session -- startlxde\n',0o755)
put('.config/lxsession/LXDE/autostart','@lxpanel --profile LXDE\n@pcmanfm --desktop --profile LXDE\n')
defaults=Path('/etc/xdg/lxsession/LXDE/desktop.conf').read_text().replace('sNet/ThemeName=Clearlooks','sNet/ThemeName=Adwaita').replace('sNet/IconThemeName=nuoveXT2','sNet/IconThemeName=Adwaita')
put('.config/lxsession/LXDE/desktop.conf',defaults)
put('.config/gtk-3.0/settings.ini','[Settings]\ngtk-theme-name=Adwaita\ngtk-icon-theme-name=Adwaita\ngtk-font-name=Sans 10\n')
put('.gtkrc-2.0','gtk-theme-name="Adwaita"\ngtk-icon-theme-name="Adwaita"\ngtk-font-name="Sans 10"\n')
put('.config/lxpanel/LXDE/panels/panel','''Global {
 edge=top
 align=left
 margin=0
 widthtype=percent
 width=100
 height=32
 transparent=0
 tintcolor=#e8e8e8
 alpha=255
 setdocktype=1
 setpartialstrut=1
 usefontcolor=1
 fontcolor=#202020
 background=0
 iconsize=24
}
Plugin {
 type=menu
 Config {
  image=/usr/share/lxde/images/lxde-icon.png
  system { }
  separator { }
  item { command=run }
  separator { }
  item { command=logout }
 }
}
Plugin {
 type=launchbar
 Config {
  Button { id=firefox-esr.desktop }
  Button { id=pcmanfm.desktop }
  Button { id=lxterminal.desktop }
 }
}
Plugin {
 type=taskbar
 expand=1
 Config {
  tooltips=1
  IconsOnly=0
  ShowAllDesks=0
  MaxTaskWidth=180
  spacing=1
 }
}
Plugin { type=tray }
Plugin {
 type=dclock
 Config {
  ClockFmt=%H:%M
  TooltipFmt=%A %d %B %Y
 }
}
'''.replace('  Button { id=firefox-esr.desktop }\n','  Button { id=firefox-esr.desktop }\n' if firefox else ''))
put('.config/pcmanfm/LXDE/pcmanfm.conf','''[config]
bm_open_method=0
[volume]
mount_on_startup=0
mount_removable=0
autorun=0
[desktop]
wallpaper_mode=crop
wallpaper=/usr/share/lxde/wallpapers/lxde_blue.jpg
desktop_bg=#24303d
desktop_fg=#ffffff
desktop_shadow=#000000
show_wm_menu=0
[ui]
win_width=900
win_height=600
side_pane_mode=places
view_mode=icon
show_hidden=0
sort=name;ascending;
''')
put('.config/pcmanfm/LXDE/desktop-items-0.conf','''[*]
wallpaper_mode=crop
wallpaper_common=1
wallpaper=/usr/share/lxde/wallpapers/lxde_blue.jpg
desktop_bg=#24303d
desktop_fg=#ffffff
desktop_shadow=#000000
desktop_font=Sans 10
show_wm_menu=0
show_documents=0
show_trash=1
show_mounts=0
''')
for name,exec_,icon,wanted in [('Home','pcmanfm "'+str(home)+'"','user-home',True),('Videos','pcmanfm "'+str(home/'Videos')+'"','folder-videos',True),('VLC','vlc','vlc',vlc),('NAS Settings','firefox-esr http://127.0.0.1/','network-server',firefox),('Screenshot','scrot --select --file "'+str(home/'Pictures/Screenshot-%%Y%%m%%d-%%H%%M%%S.png')+'"','camera-photo',scrot)]:
    f=home/'Desktop'/(name+'.desktop')
    if wanted:put('Desktop/'+name+'.desktop',f'[Desktop Entry]\nType=Application\nName={name}\nExec={exec_}\nIcon={icon}\nTerminal=false\n',0o755)
    elif f.exists():old=backup/'Desktop'/f.name;own_parents(old.parent);shutil.move(f,old)
if Path('/usr/local/share/doc/lincstation/README.md').is_file():
    viewer='mousepad /usr/local/share/doc/lincstation/README.md' if mousepad else 'lxterminal -e lincstation-help'
    put('Desktop/LincStation Guide.desktop',f'[Desktop Entry]\nType=Application\nName=LincStation Guide\nExec={viewer}\nIcon=help-browser\nTerminal=false\n',0o755)
mkdir('Pictures')
put('.config/user-dirs.dirs','XDG_DESKTOP_DIR="$HOME/Desktop"\nXDG_DOWNLOAD_DIR="$HOME/Downloads"\nXDG_VIDEOS_DIR="$HOME/Videos"\nXDG_PICTURES_DIR="$HOME/Pictures"\n')
rc=Path('/etc/xdg/openbox/LXDE/rc.xml').read_text()
put('.config/openbox/lxde-rc.xml',rc)
put('.config/mimeapps.list','[Default Applications]\n'+(''.join('video/'+t+'=vlc.desktop\n' for t in ['mp4','x-matroska','webm','quicktime','x-msvideo']) if vlc else '')+('text/plain=org.xfce.mousepad.desktop\n' if mousepad else ''))
put('Desktop-README.txt','Log in locally and run startx for LXDE.\nThe full guide for this NAS opens from the LincStation Guide desktop icon, or run lincstation-help in a terminal.\nThe top-left menu contains apps and settings.'+(' VLC is the default video player; mpv remains available.' if vlc else '')+'\n'+(''if firefox else 'No web browser is installed; open the OMV web interface from another computer.\n')+'GPU rendering uses the installed Panfrost graphics driver.\n\nHardware video playback: VLC and mpv decode video on the CPU. To decode H.264 and MPEG-2 (up to 1080p) and VP8 in hardware, install GStreamer and a GStreamer player:\n  sudo apt-get install --no-install-recommends gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav parole\nThen open videos in Parole (Sound & Video menu). GStreamer picks the hardware decoder automatically. HEVC/H.265, VP9 and 4K H.264 always decode on the CPU.\n\nOMV storage/network settings remain in the web interface. Desktop automount/autorun is disabled.\nNo display manager or automatic desktop startup is installed.\n')
if a.live:
    ids=subprocess.run(['pgrep','-u',str(u.pw_uid),'-x','openbox'],capture_output=True,text=True).stdout.split()
    if len(ids)!=1:raise SystemExit('Configured next startx; live update needs exactly one running Openbox session.')
    envs={part.split('=',1)[0]:part.split('=',1)[1] for part in Path('/proc/'+ids[0]+'/environ').read_bytes().decode().split('\0') if '=' in part}
    env={k:envs[k] for k in ['DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS','XDG_RUNTIME_DIR'] if k in envs}
    env.update(HOME=str(home),XDG_CURRENT_DESKTOP='LXDE',XDG_MENU_PREFIX='lxde-')
    subprocess.run(['pkill','-u',str(u.pw_uid),'-x','tint2'],check=False)
    log=open('/tmp/lincstation-lxde-live.log','ab')
    commands=[['pcmanfm','--desktop','--profile','LXDE']]
    if subprocess.run(['pgrep','-u',str(u.pw_uid),'-x','lxpanel'],stdout=subprocess.DEVNULL).returncode:
        commands.insert(0,['lxpanel','--profile','LXDE'])
    for cmd in commands:
        subprocess.Popen(['runuser','-u',a.user,'--','env',*[k+'='+v for k,v in env.items()],*cmd],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    print('Panel/desktop updated live; full LXDE session starts on next startx. Existing applications were preserved.')
print('LXDE configured for',a.user,'; prior settings backed up under',backup)
