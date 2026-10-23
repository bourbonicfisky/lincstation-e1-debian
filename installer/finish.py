#!/usr/bin/env python3
"""Client-side finishing step; credentials never appear in shell arguments."""
import json,secrets,shlex,subprocess,sys,urllib.request
from pathlib import Path
from e1lib import save,require,software_options,DEFAULT_SOFTWARE
BASE=Path(__file__).resolve().parent
work=Path(sys.argv[1]).resolve();p=json.loads((work/'plan.json').read_text())
sw=software_options(**(json.loads(sys.argv[2]) if len(sys.argv)>2 else DEFAULT_SOFTWARE))
credsfile=work/'credentials.json'
if not credsfile.exists():
    short=''.join(secrets.choice('abcdefghijkmnopqrstuvwxyz23456789') for _ in range(8))
    save(credsfile,dict(console=short,vnc=short,admin=secrets.token_urlsafe(18)))
creds=json.loads(credsfile.read_text())
ssh=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ServerAliveInterval=15','-o','UserKnownHostsFile='+str(work/'installed-known_hosts'),'-i',str(work/'owner-key'),'root@'+p['nas_ip']]
dest='/tmp/e1-finish-'+p['run_id'];subprocess.run(ssh+['umask 077; mkdir -p '+dest],check=True)
for name in ['finish-device.py','e1lib.py','install-desktop.sh','configure-desktop.py','setup-vnc.py']:
    subprocess.run(ssh+['cat > '+dest+'/'+name],input=(BASE/name).read_bytes(),check=True)
with (work/'finish.log').open('a') as log:
    subprocess.run(ssh+['python3 '+dest+'/finish-device.py'],input=json.dumps(dict(creds,software=sw)),text=True,stdout=log,stderr=subprocess.STDOUT,check=True)
# Check web login on the NAS loopback, without sending a password over unencrypted LAN HTTP.
code="""import json,sys,urllib.request
c=json.load(sys.stdin)
body=json.dumps({'service':'Session','method':'login','params':{'username':'admin','password':c['admin']}}).encode()
r=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1/rpc.php',body,{'Content-Type':'application/json'}),timeout=20))
if r.get('error') or r.get('response',{}).get('status')!='authenticated':raise RuntimeError('OMV login failed')
print('OMV login verified')
"""
subprocess.run(ssh+['python3 -c '+shlex.quote(code)],input=json.dumps(creds),text=True,check=True)
subprocess.run([*ssh[:-1],p['user']+'@'+p['nas_ip'],'id'],check=True)
text='LincStation E1 private credentials\n\nOMV: http://'+p['nas_ip']+'/\nUsername: admin\nPassword: '+creds['admin']+'\n\nConsole: '+p['user']+'\nPassword: '+creds['console']+'\n'+('Run startx for LXDE.\n' if sw['desktop'] else '')+'\n'
if sw['vnc']:text+='VNC password: '+creds['vnc']+'\nVNC requires an active HDMI desktop and SSH tunnel.\n'
text+='SSH key: '+str(work/'owner-key')+'\n'
(work/'LOGIN.txt').write_text(text);(work/'LOGIN.txt').chmod(0o600)
print('Setup verified. Private credentials:',work/'LOGIN.txt')
if sw['desktop']:
    print('\nHardware video playback: VLC and mpv decode on the CPU. For hardware H.264/MPEG-2 (up to 1080p) and VP8 decoding,')
    print('install GStreamer and a GStreamer player on the NAS, then play videos in Parole:')
    print('  sudo apt-get install --no-install-recommends gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav parole')
print('Keep finish.log and the entire private work directory; do not distribute them.')
