"""Tests characterize legacy behavior, not certify correctness of BaZi."""
import unittest,sys,os,time,math,calendar
from pathlib import Path
from datetime import datetime,date
# Run from workspace with inspected original code and vendored lunar-python 1.4.4.
sys.path[:0]=[os.environ.get('BAZI_AUDIT_VENDOR','audit/vendor'),os.environ.get('BAZI_AUDIT_BACKEND','legacy/bazi/backend')]
import bazi
from lunar_python import Solar
class AuditObservations(unittest.TestCase):
 def calc(self,s):return bazi.compute_bazi_local(bazi.InputArgs(datetime.fromisoformat(s),'Asia/Ho_Chi_Minh','M','standard'))
 def test_01_naive_host_timezone_changes_hour(self):
  out=[];prev=os.environ.get('TZ')
  try:
   for tz in ['UTC','Asia/Ho_Chi_Minh']:
    os.environ['TZ']=tz;time.tzset();out.append(self.calc('2000-06-15T05:30:00')['trụ']['giờ'])
   self.assertNotEqual(out[0],out[1])
  finally:
   if prev is None:os.environ.pop('TZ',None)
   else:os.environ['TZ']=prev
   time.tzset()
 def test_02_aware_keeps_clock(self):
  x=self.calc('2000-06-15T05:30:00+07:00');self.assertEqual(x['đầu_vào']['thời_điểm_tính'],'2000-06-15T05:30:00+07:00')
 def test_03_unknown_timezone_silent_fallback(self):self.assertEqual(str(bazi.resolve_timezone('Invalid/Zone')),'UTC')
 def test_04_eot_differs_from_noaa_reference(self):
  d=date(2024,2,11);g=2*math.pi/366*(d.timetuple().tm_yday-1)
  ref=229.18*(.000075+.001868*math.cos(g)-.032077*math.sin(g)-.014615*math.cos(2*g)-.040849*math.sin(2*g))
  self.assertGreater(abs(bazi.equation_of_time_minutes(d)-ref),27)
 def test_05_january_liu_nian_keeps_previous_year_stem(self):
  x=self.calc('2024-01-15T12:00:00+07:00');self.assertEqual(x['lưu_niên'][1]['can_chi'],'Giáp Thìn');self.assertEqual(x['lưu_niên'][1]['năm_dương'],2025)
 def test_06_thai_nguyen_matches_library_12_months(self):
  for m in range(1,13):
   e=Solar.fromYmdHms(2024,m,15,12,0,0).getLunar().getEightChar();pair=bazi.cn_ganzhi_to_vi_pair(e.getMonth())
   self.assertEqual(bazi.tinh_thai_nguyen(*pair),bazi.cn_ganzhi_to_vi_pair(e.getTaiYuan()))
 def test_07_two_members_reported_in_tam_hop(self):
  self.assertEqual(len(bazi.phan_tich_quan_he_chi(['Thân','Tý','Mão','Ngọ'])['tam_hợp']),1)
 def test_08_ten_luck_cycles_smoke(self):self.assertEqual(len(self.calc('2000-06-15T05:30:00+07:00')['đại_vận']['các_chu_kỳ']),10)
 def test_09_leapday_smoke(self):self.assertEqual(len(self.calc('2024-02-29T12:00:00+07:00')['trụ']),4)
if __name__=='__main__':unittest.main(verbosity=2)
