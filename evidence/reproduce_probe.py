import sys,os,time,json,math,hashlib
from pathlib import Path
from datetime import datetime,date
sys.path[:0]=[os.environ.get('BAZI_AUDIT_VENDOR','audit/vendor'),os.environ.get('BAZI_AUDIT_BACKEND','legacy/bazi/backend')]
import bazi
from lunar_python import Solar
r={}
def calc(dt):return bazi.compute_bazi_local(bazi.InputArgs(datetime.fromisoformat(dt),'Asia/Ho_Chi_Minh','M','standard'))
for tz in ['UTC','Asia/Ho_Chi_Minh']:
 os.environ['TZ']=tz;time.tzset()
 x=calc('2000-06-15T05:30:00');r['naive_host_'+tz]={'input':x['đầu_vào'],'pillars':{k:v['can']+' '+v['chi'] for k,v in x['trụ'].items()}}
os.environ['TZ']='UTC';time.tzset()
x=calc('2000-06-15T05:30:00+07:00');r['aware']={'input':x['đầu_vào'],'pillars':{k:v['can']+' '+v['chi'] for k,v in x['trụ'].items()},'luck_count':len(x['đại_vận']['các_chu_kỳ'])}
x=calc('2024-01-15T12:00:00+07:00');r['liu_nian_jan2024']=x['lưu_niên'][:2]
r['thai_nguyen']=[{'month':g+c,'legacy':bazi.tinh_thai_nguyen(g,c),'library':bazi.cn_ganzhi_to_vi_pair(Solar.fromYmdHms(y,m,15,12,0,0).getLunar().getEightChar().getTaiYuan())} for y,m in [(2024,i) for i in range(1,13)] for g,c in [bazi.cn_ganzhi_to_vi_pair(Solar.fromYmdHms(y,m,15,12,0,0).getLunar().getEightChar().getMonth())]]
r['invalid_timezone']=str(bazi.resolve_timezone('Invalid/Zone'))
r['eot']={str(d):bazi.equation_of_time_minutes(d) for d in [date(2024,2,11),date(2024,11,3)]}
r['relation_two_members']=bazi.phan_tich_quan_he_chi(['Thân','Tý','Mão','Ngọ'])['tam_hợp']
r['smoke']=[]
for dt in ['2024-02-29T12:00:00+07:00','2024-02-04T15:30:00+07:00','2024-02-04T16:30:00+07:00','2024-06-01T23:30:00+07:00','2024-06-02T00:30:00+07:00']:
 x=calc(dt);r['smoke'].append({'dt':dt,'pillars':{k:v['can']+' '+v['chi'] for k,v in x['trụ'].items()}})
r['lichun_library_civil']=Solar.fromYmd(2024,2,4).getLunar().getJieQiTable()['立春'].toYmdHms()
Path(os.environ.get('BAZI_AUDIT_OUTPUT','probe_results.json')).write_text(json.dumps(r,ensure_ascii=False,indent=2))
print(json.dumps(r,ensure_ascii=False,indent=2))
