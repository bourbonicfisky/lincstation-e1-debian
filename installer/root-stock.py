#!/usr/bin/env python3
"""Owner-authorized ADB/aria2 bootstrap into the stock LincSeed root chroot."""
import http.server,json,subprocess,sys,threading,time,urllib.request
from pathlib import Path
from e1lib import require,run

def bootstrap(work,config):
    adb=['adb','-s',config['adb_serial']]
    subprocess.run(['adb','connect',config['adb_serial']],check=True)
    def shell(command):return run(*adb,'shell',command)
    require(shell('getenforce').strip()=='Permissive','This method was tested only with SELinux Permissive')
    require(shell('getprop ro.boot.verifiedbootstate').strip()=='orange','Expected unlocked bootloader (verifiedbootstate orange)')
    pub=(work/'owner-key.pub').read_text().strip()
    require(pub.startswith('ssh-ed25519 ') and '\n' not in pub,'Expected generated Ed25519 key')
    name='e1-migrate-'+config['run_id'];directory='/root/'+name;android='/data/local/tmp/'+name
    script='''#!/bin/sh
set -eu
umask 077
D=DIR
mkdir -p "$D" /run/sshd
chmod 700 "$D"
cat > "$D/authorized_keys" <<'KEY'
PUBKEY
KEY
if [ ! -f "$D/ssh_host_ed25519_key" ]; then ssh-keygen -q -t ed25519 -N '' -f "$D/ssh_host_ed25519_key"; fi
cat > "$D/sshd_config" <<'CONF'
Port 2222
ListenAddress 127.0.0.1
HostKey DIR/ssh_host_ed25519_key
PidFile DIR/sshd.pid
AuthorizedKeysFile DIR/authorized_keys
PermitRootLogin prohibit-password
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
UsePAM yes
AllowUsers root
AllowTcpForwarding no
X11Forwarding no
PermitTunnel no
Subsystem sftp internal-sftp
CONF
/usr/sbin/sshd -t -f "$D/sshd_config"
if [ ! -f "$D/sshd.pid" ] || ! kill -0 "$(cat "$D/sshd.pid")" 2>/dev/null; then
 /usr/sbin/sshd -f "$D/sshd_config" -E "$D/sshd.log"
fi
cat "$D/ssh_host_ed25519_key.pub" > /proc/1/root/ANDROID.ready
chmod 644 /proc/1/root/ANDROID.ready
'''.replace('DIR',directory).replace('PUBKEY',pub).replace('ANDROID',android)
    payload=work/'stock-setup.sh';payload.write_text(script)
    subprocess.run(adb+['push',str(payload),android+'.sh'],check=True)
    cfg=shell('cat /mnt/roLincOS/etc/aria2/aria2.conf')
    secret=next(line.split('=',1)[1].strip() for line in cfg.splitlines() if line.strip().startswith('rpc-secret='))
    subprocess.run(adb+['forward','tcp:16800','tcp:6800'],check=True)
    cron=('SHELL=/bin/sh\nPATH=/usr/sbin:/usr/bin:/sbin:/bin\n* * * * * root rm -f /etc/cron.d/'+name+'; /bin/sh /proc/1/root'+android+'.sh > /proc/1/root'+android+'.log 2>&1\n').encode()
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path!='/cron':self.send_error(404);return
            self.send_response(200);self.send_header('Content-Length',str(len(cron)));self.end_headers();self.wfile.write(cron)
        def log_message(self,*args):pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',18081),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    def rpc(method,*params):
        req=urllib.request.Request('http://127.0.0.1:16800/jsonrpc',json.dumps({'jsonrpc':'2.0','id':name,'method':method,'params':['token:'+secret,*params]}).encode(),{'Content-Type':'application/json'})
        response=json.load(urllib.request.urlopen(req,timeout=10));require('error' not in response,'aria2 RPC failed');return response['result']
    try:
        subprocess.run(adb+['reverse','tcp:18081','tcp:18081'],check=True)
        gid=rpc('aria2.addUri',['http://127.0.0.1:18081/cron'],{'dir':'/etc/cron.d','out':name,'allow-overwrite':'true','auto-file-renaming':'false','max-tries':'1','split':'1','max-connection-per-server':'1','file-allocation':'none'})
        for i in range(30):
            state=rpc('aria2.tellStatus',gid,['status'])['status']
            if state in ('complete','error','removed'):break
            time.sleep(.5)
        require(state=='complete','Cron delivery failed');rpc('aria2.removeDownloadResult',gid)
    finally:
        server.shutdown();subprocess.run(adb+['reverse','--remove','tcp:18081'],check=False)
        subprocess.run(adb+['forward','--remove','tcp:16800'],check=False)
    for i in range(90):
        result=subprocess.run(adb+['shell','cat '+android+'.ready'],capture_output=True,text=True)
        key=result.stdout.strip()
        if result.returncode==0 and key.startswith('ssh-ed25519 '):break
        time.sleep(1)
    else:raise RuntimeError('Root bootstrap timed out. Inspect '+android+'.log using adb; no boot partitions have been written.')
    subprocess.run(adb+['forward','tcp:22222','tcp:2222'],check=True)
    (work/'stock-known_hosts').write_text('[127.0.0.1]:22222 '+' '.join(key.split()[:2])+'\n')
    print('Stock root SSH established; host key pinned from the authorized ADB connection.')
if __name__=='__main__':
    work=Path(sys.argv[1]).resolve();bootstrap(work,json.loads((work/'config.json').read_text()))
