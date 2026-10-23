"""Common E1 formats and guards. No device-specific credentials are distributed."""
import gzip,hashlib,json,os,stat,struct,subprocess,zlib
from pathlib import Path
BOOT_SIZE=157286400
EMMC_SIZE=62545461248
ROOT_SIZE=50643042304
ROOT_PARTUUID='43580000-0000-4463-8000-4fd300004373'
KERNEL='6.12.113+deb13-arm64'
STOCK={'boot_b.img':'78e4ceaac9c714a68859f00a4aaee1c3bd18d435eb935ed22198243d46b753da','dtbo_b.img':'59b971b4300092de56164904d6a1747276eb569acfc31c09dda6569aa5c8e57d','uboot_b.img':'fa9a48ed3b4ff7032b96511c4dbc4d80b076873f1051e61eda3687124e369f56'}
DTB_SHA='1fce124bfe67804135ad04f40756754aa7b149fab9794a9dfc3f2716848da933'
def require(ok,message):
    if not ok:raise RuntimeError(message)
def run(*args,**kw):return subprocess.check_output(list(map(str,args)),text=True,**kw).strip()
def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        while block:=f.read(4194304):h.update(block)
    return h.hexdigest()
def save(path,value):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.chmod(0o600);tmp.replace(path)
def read_ab(sector):
    require(len(sector)==512,'Incomplete A/B sector')
    data=sector[:32]
    require(data[:4]==b'\0AB0' and data[4]==1,'Unsupported A/B metadata')
    require(zlib.crc32(data[:28])==struct.unpack('>I',data[28:])[0],'Invalid A/B CRC')
    return list(data[8:12]),list(data[12:16])
def update_ab(sector,a,b):
    read_ab(sector)
    for slot in (a,b):
        require(len(slot)==4 and 0<=slot[0]<=15 and 0<=slot[1]<=7 and slot[2] in (0,1) and slot[3]==0,'Invalid slot fields')
    data=bytearray(sector);data[8:12]=bytes(a);data[12:16]=bytes(b);data[28:32]=struct.pack('>I',zlib.crc32(data[:28]));return bytes(data)
def write_ab(path,a,b):
    with open(path,'r+b',buffering=0) as f:
        f.seek(2048);new=update_ab(f.read(512),a,b);f.seek(2048)
        require(f.write(new)==512,'Short A/B write');os.fsync(f.fileno());f.seek(2048);require(f.read(512)==new,'A/B readback mismatch')
def padded_image(path):
    data=Path(path).read_bytes()
    require(data[:8]==b'ANDROID!' and len(data)<=BOOT_SIZE,'Invalid or oversized Android image')
    require(struct.unpack_from('<I',data,40)[0]==2,'Expected Android header v2')
    return data+b'\0'*(BOOT_SIZE-len(data))
def image_record(path):return {'sha256':sha(path),'bytes':Path(path).stat().st_size,'padded_sha256':hashlib.sha256(padded_image(path)).hexdigest()}
def write_image(path,image,record):
    require(sha(image)==record['sha256'],'Payload hash mismatch')
    data=padded_image(image);require(hashlib.sha256(data).hexdigest()==record['padded_sha256'],'Padded hash mismatch')
    require(int(run('blockdev','--getsize64',path))==BOOT_SIZE,'Unexpected boot partition size')
    with open(path,'r+b',buffering=0) as f:require(f.write(data)==len(data),'Short boot write');os.fsync(f.fileno())
    require(sha(path)==record['padded_sha256'],'Boot partition readback mismatch')
def cpio(root,out):
    root=Path(root)
    require((root/'init').is_file() and (root/'init').stat().st_mode&0o111,'/init must be executable')
    require((root/'bin/busybox').is_file() and os.access(root/'bin/busybox',os.X_OK),'Missing executable init interpreter')
    entries=[]
    for f in sorted(root.rglob('*')):
        name=str(f.relative_to(root));st=f.lstat()
        if name in ('dev/null','dev/console'):continue
        require(stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode),'Unexpected special file: '+name)
        data=os.readlink(f).encode() if f.is_symlink() else f.read_bytes() if f.is_file() else b''
        entries.append((name,st.st_mode,data,0,0))
    entries += [('dev/console',stat.S_IFCHR|0o600,b'',5,1),('dev/null',stat.S_IFCHR|0o666,b'',1,3),('TRAILER!!!',0,b'',0,0)]
    with open(out,'wb') as raw,gzip.GzipFile(filename='',fileobj=raw,mode='wb',compresslevel=1,mtime=0) as z:
        for ino,(name,mode,data,major,minor) in enumerate(entries,1):
            nb=name.encode()+b'\0';fields=[ino,mode,0,0,2 if stat.S_ISDIR(mode) else 1,0,len(data),0,0,major,minor,len(nb),0]
            header=b'070701'+b''.join(f'{v:08x}'.encode() for v in fields)+nb
            z.write(header+b'\0'*(-len(header)%4)+data+b'\0'*(-len(data)%4))
# Optional software on top of OMV. Group names must match install-desktop.sh.
APP_GROUPS={'web':'Web browser (Firefox ESR)','media':'Media players (VLC, mpv, FFmpeg, ALSA tools)','utilities':'Utilities (text editor, image viewer, archives, calculator, screenshots, htop)'}
DEFAULT_SOFTWARE={'desktop':True,'apps':list(APP_GROUPS),'vnc':True}
def software_options(desktop=True,apps=None,vnc=True):
    apps=list(APP_GROUPS) if apps is None else [g for g in APP_GROUPS if g in apps]
    if not desktop:return {'desktop':False,'apps':[],'vnc':False}
    return {'desktop':True,'apps':apps,'vnc':bool(vnc)}
def parse_apps(text):
    names=[g.strip() for g in text.split(',') if g.strip()]
    if names in (['all'],):return list(APP_GROUPS)
    if names in (['none'],[]):return []
    unknown=[g for g in names if g not in APP_GROUPS];require(not unknown,'Unknown app group: '+', '.join(unknown)+' (choose '+', '.join(APP_GROUPS)+', all or none)')
    return names
def choose_software(current=None,ask=input,say=print):
    """Terminal checklist: type item numbers to toggle, Enter to accept."""
    s=dict(current or DEFAULT_SOFTWARE);s['apps']=list(s['apps'])
    items=[('desktop','Desktop (LXDE on HDMI, started with startx)')]+[('app:'+g,label) for g,label in APP_GROUPS.items()]+[('vnc','Remote desktop (VNC through an SSH tunnel)')]
    while True:
        say('\nOpenMediaVault is always installed. Choose the extras:')
        for n,(key,label) in enumerate(items,1):
            on=s['desktop'] if key=='desktop' else key[4:] in s['apps'] if key.startswith('app:') else s['vnc']
            box='[-]' if key!='desktop' and not s['desktop'] else '[x]' if on else '[ ]'
            say(f'  {box} {n}  '+('' if key=='desktop' else '  ')+label)
        answer=ask('Numbers to toggle (e.g. "3 5"), or Enter to accept: ').strip()
        if not answer:return software_options(s['desktop'],s['apps'],s['vnc'])
        for token in answer.replace(',',' ').split():
            if not token.isdigit() or not 1<=int(token)<=len(items):say('Ignoring '+repr(token));continue
            key=items[int(token)-1][0]
            if key=='desktop':s['desktop']=not s['desktop']
            elif not s['desktop']:say('Turn the desktop on first to choose '+items[int(token)-1][1].split(' (')[0].lower())
            elif key=='vnc':s['vnc']=not s['vnc']
            else:
                g=key[4:];s['apps']=[x for x in s['apps'] if x!=g] if g in s['apps'] else [x for x in APP_GROUPS if x in s['apps'] or x==g]
