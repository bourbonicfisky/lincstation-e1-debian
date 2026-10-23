import gzip,hashlib,importlib.util,json,os,stat,struct,sys,tempfile,unittest,zlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import e1lib as lib
import device
class Formats(unittest.TestCase):
    def sector(self):
        b=bytearray(512);b[:5]=b'\0AB0\x01';b[8:12]=bytes([0,0,0,0]);b[12:16]=bytes([15,0,1,0]);b[28:32]=struct.pack('>I',zlib.crc32(b[:28]));b[32:]=os.urandom(480);return bytes(b)
    def test_trial_two_preserves_unrelated_sector(self):
        old=self.sector();new=lib.update_ab(old,[15,2,0,0],[14,0,1,0]);self.assertEqual(new[32:],old[32:]);self.assertEqual(lib.read_ab(new),([15,2,0,0],[14,0,1,0]))
    def test_bad_crc_refused(self):
        b=bytearray(self.sector());b[8]^=1
        with self.assertRaises(RuntimeError):lib.update_ab(b,[15,2,0,0],[14,0,1,0])
    def test_metadata_write_only_one_sector(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'misc';original=os.urandom(2048)+self.sector()+os.urandom(1000);f.write_bytes(original)
            lib.write_ab(f,[15,2,0,0],[14,0,1,0]);new=f.read_bytes();self.assertEqual(new[:2048],original[:2048]);self.assertEqual(new[2560:],original[2560:])
    def test_image_rejects_oversize_and_wrong_header(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'boot';f.write_bytes(b'ANDROID!'+bytes(100))
            with self.assertRaises(RuntimeError):lib.padded_image(f)
            b=bytearray(100);b[:8]=b'ANDROID!';struct.pack_into('<I',b,40,2);f.write_bytes(b)
            with patch.object(lib,'BOOT_SIZE',80):
                with self.assertRaises(RuntimeError):lib.padded_image(f)
    def test_nonexecutable_init_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'init').write_text('#!/bin/busybox sh\n');(root/'init').chmod(0o644)
            with self.assertRaisesRegex(RuntimeError,'executable'):lib.cpio(root,root/'out.gz')
    def test_cpio_contains_executable_init_and_devices(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d)/'root';r.mkdir();(r/'bin').mkdir();(r/'init').write_text('#!/bin/busybox sh\n');(r/'init').chmod(0o755);(r/'bin/busybox').write_bytes(b'example');(r/'bin/busybox').chmod(0o755)
            out=Path(d)/'test.gz';lib.cpio(r,out);data=gzip.decompress(out.read_bytes());i=0;entries={}
            while True:
                self.assertEqual(data[i:i+6],b'070701');fields=[int(data[i+6+n*8:i+14+n*8],16) for n in range(13)];name=data[i+110:i+110+fields[11]-1].decode();payload=(i+110+fields[11]+3)&~3;entries[name]=fields;i=(payload+fields[6]+3)&~3
                if name=='TRAILER!!!':break
            self.assertEqual(stat.S_IMODE(entries['init'][1]),0o755);self.assertEqual(entries['dev/console'][9:11],[5,1]);self.assertEqual(entries['dev/null'][9:11],[1,3])
    def test_wrong_device_stops_before_any_write(self):
        import io
        request={'action':'stage-a','plan':{'emmc_cid':'expected'}}
        with patch.object(device,'probe',return_value={'emmc_cid':'wrong'}),patch('sys.stdin',io.StringIO(json.dumps(request))),patch.object(device,'write_ab') as metadata,patch.object(device,'write_image') as image:
            with self.assertRaisesRegex(RuntimeError,'identity'):device.main()
            metadata.assert_not_called();image.assert_not_called()
    def test_wrong_stock_boot_stops_before_any_write(self):
        import io
        p={'emmc_cid':'expected','stock':True,'cmdline':'androidboot.slot_suffix=_b','slot_b':[15,0,1,0],'device':'/dev/block/mmcblk2'}
        request={'action':'stage-a','plan':{'emmc_cid':'expected'},'manifest':{'recovery':{},'installed':{}}}
        with patch.object(device,'probe',return_value=p),patch('sys.stdin',io.StringIO(json.dumps(request))),patch.object(device,'sha',return_value='wrong'),patch.object(device,'write_ab') as metadata,patch.object(device,'write_image') as image:
            with self.assertRaisesRegex(RuntimeError,'Unknown stock'):device.main()
            metadata.assert_not_called();image.assert_not_called()
class Software(unittest.TestCase):
    def menu(self,*answers):
        it=iter(answers);return lib.choose_software(ask=lambda prompt:next(it),say=lambda *a:None)
    def test_enter_accepts_everything(self):
        self.assertEqual(self.menu(''),{'desktop':True,'apps':['web','media','utilities'],'vnc':True})
    def test_toggle_groups(self):
        self.assertEqual(self.menu('3 5',''),{'desktop':True,'apps':['web','utilities'],'vnc':False})
        self.assertEqual(self.menu('2','2',''),{'desktop':True,'apps':['web','media','utilities'],'vnc':True})
    def test_no_desktop_clears_extras(self):
        self.assertEqual(self.menu('1','4',''),{'desktop':False,'apps':[],'vnc':False})
        self.assertEqual(lib.software_options(False,['web'],True),{'desktop':False,'apps':[],'vnc':False})
    def test_parse_apps(self):
        self.assertEqual(lib.parse_apps('utilities, web'),['utilities','web'])
        self.assertEqual(lib.parse_apps('all'),list(lib.APP_GROUPS));self.assertEqual(lib.parse_apps('none'),[])
        with self.assertRaisesRegex(RuntimeError,'Unknown app group'):lib.parse_apps('web,games')
if __name__=='__main__':unittest.main()
