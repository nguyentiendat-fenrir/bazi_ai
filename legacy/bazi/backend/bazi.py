##run python bazi.py --dt 2002-10-06T05:30:00 --gender M

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, date, timedelta, timezone
from typing import Dict, List, Tuple, Optional

# zoneinfo có thể thiếu tzdata trên Windows; đã có fallback
try:
    import zoneinfo  # type: ignore
except Exception:
    zoneinfo = None  # type: ignore

from lunar_python import Solar

# =========================
# BẢN ĐỒ CAN/CHI & NGŨ HÀNH (TIẾNG VIỆT)
# =========================
CAN_VI = ["Giáp","Ất","Bính","Đinh","Mậu","Kỷ","Canh","Tân","Nhâm","Quý"]
CHI_VI = ["Tý","Sửu","Dần","Mão","Thìn","Tỵ","Ngọ","Mùi","Thân","Dậu","Tuất","Hợi"]
CHI_THANG = ["Dần","Mão","Thìn","Tỵ","Ngọ","Mùi","Thân","Dậu","Tuất","Hợi","Tý","Sửu"]
TRUONG_SINH =["Trường sinh", "Mộc dục", "Quan đới", "Lâm quan", "Đế vượng", "Suy", "Bệnh", "Tử", "Mộ", "Tuyệt", "Thai", "Dưỡng"]
NAP_AM_LUC_THAP_HOA_GIAP = {
    "Giáp Tý": "Hải trung Kim", "Ất Sửu": "Hải trung Kim",
    "Bính Dần": "Lư trung Hỏa", "Đinh Mão": "Lư trung Hỏa",
    "Mậu Thìn": "Đại lâm Mộc", "Kỷ Tỵ": "Đại lâm Mộc",
    "Canh Ngọ": "Lộ bàng Thổ", "Tân Mùi": "Lộ bàng Thổ",
    "Nhâm Thân": "Kiếm phong Kim", "Quý Dậu": "Kiếm phong Kim",
    "Giáp Tuất": "Sơn đầu Hỏa", "Ất Hợi": "Sơn đầu Hỏa",
    "Bính Tý": "Giản hạ Thủy", "Đinh Sửu": "Giản hạ Thủy",
    "Mậu Dần": "Thành đầu Thổ", "Kỷ Mão": "Thành đầu Thổ",
    "Canh Thìn": "Bạch lạp Kim", "Tân Tỵ": "Bạch lạp Kim",
    "Nhâm Ngọ": "Dương liễu Mộc", "Quý Mùi": "Dương liễu Mộc",
    "Giáp Thân": "Tuyền trung Thủy", "Ất Dậu": "Tuyền trung Thủy",
    "Bính Tuất": "Ốc thượng Thổ", "Đinh Hợi": "Ốc thượng Thổ",
    "Mậu Tý": "Tích lịch Hỏa", "Kỷ Sửu": "Tích lịch Hỏa",
    "Canh Dần": "Tùng bách Mộc", "Tân Mão": "Tùng bách Mộc",
    "Nhâm Thìn": "Trường lưu Thủy", "Quý Tỵ": "Trường lưu Thủy",
    "Giáp Ngọ": "Sa trung Kim", "Ất Mùi": "Sa trung Kim",
    "Bính Thân": "Sơn hạ Hỏa", "Đinh Dậu": "Sơn hạ Hỏa",
    "Mậu Tuất": "Bình địa Mộc", "Kỷ Hợi": "Bình địa Mộc",
    "Canh Tý": "Bích thượng Thổ", "Tân Sửu": "Bích thượng Thổ",
    "Nhâm Dần": "Kim bạch Kim", "Quý Mão": "Kim bạch Kim",
    "Giáp Thìn": "Phúc đăng Hỏa", "Ất Tỵ": "Phúc đăng Hỏa",
    "Bính Ngọ": "Thiên hà Thủy", "Đinh Mùi": "Thiên hà Thủy",
    "Mậu Thân": "Đại dịch Thổ", "Kỷ Dậu": "Đại dịch Thổ",
    "Canh Tuất": "Thoa xuyến Kim", "Tân Hợi": "Thoa xuyến Kim",
    "Nhâm Tý": "Tang đố Mộc", "Quý Sửu": "Tang đố Mộc",
    "Giáp Dần": "Đại khê Thủy", "Ất Mão": "Đại khê Thủy",
    "Bính Thìn": "Sa trung Thổ", "Đinh Tỵ": "Sa trung Thổ",
    "Mậu Ngọ": "Thiên thượng Hỏa", "Kỷ Mùi": "Thiên thượng Hỏa",
    "Canh Thân": "Thạch lựu Mộc", "Tân Dậu": "Thạch lựu Mộc",
    "Nhâm Tuất": "Đại hải Thủy", "Quý Hợi": "Đại hải Thủy"
}

# Bảng tra Can tháng theo Can năm (theo ảnh bạn gửi)
CAN_THANG_THEO_CAN_NAM = {
    "Giáp":  ["Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý", "Giáp", "Ất", "Bính", "Đinh"],
    "Kỷ":    ["Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý", "Giáp", "Ất", "Bính", "Đinh"],
    "Ất":    ["Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý", "Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ"],
    "Canh":  ["Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý", "Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ"],
    "Bính":  ["Canh", "Tân", "Nhâm", "Quý", "Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân"],
    "Tân":   ["Canh", "Tân", "Nhâm", "Quý", "Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân"],
    "Đinh":  ["Nhâm", "Quý", "Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý"],
    "Nhâm":  ["Nhâm", "Quý", "Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý"],
    "Mậu":   ["Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý", "Giáp", "Ất"],
    "Quý":   ["Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý", "Giáp", "Ất"],
}

def tinh_cung_menh_full(can_nam: str, chi_thang: str, chi_gio: str) -> Tuple[str, str]:
    """
    Trả về (can, chi) của cung mệnh theo quy tắc:
    - Địa chi: dùng công thức 26 - (số nguyệt chi + số thời chi)
    - Can: tra bảng theo can năm và vị trí địa chi vừa tìm
    """
    chi_so = {chi: i+1 for i, chi in enumerate(CHI_THANG)}  # Dần=1,...,Sửu=12
    nguyet = chi_so.get(chi_thang, 0)
    thoi = chi_so.get(chi_gio, 0)
    A = 26 - (nguyet + thoi)
    B = A if A <= 12 else A - 12
    if B < 1 or B > 12:
        return ("N/A", "N/A")
    chi_cung = CHI_THANG[B-1]
    # Tra can theo bảng
    can_list = CAN_THANG_THEO_CAN_NAM.get(can_nam, [])
    can_cung = can_list[B-1] if can_list and len(can_list) >= B else "N/A"
    return (can_cung, chi_cung)

#Không Vong
KHONG_VONG_TUAN = [
    (["Giáp Tý", "Ất Sửu", "Bính Dần", "Đinh Mão", "Mậu Thìn", "Kỷ Tỵ", "Canh Ngọ", "Tân Mùi", "Nhâm Thân", "Quý Dậu"], ["Tuất", "Hợi"]),
    (["Giáp Tuất", "Ất Hợi", "Bính Tý", "Đinh Sửu", "Mậu Dần", "Kỷ Mão", "Canh Thìn", "Tân Tỵ", "Nhâm Ngọ", "Quý Mùi"], ["Thân", "Dậu"]),
    (["Giáp Thân", "Ất Dậu", "Bính Tuất", "Đinh Hợi", "Mậu Tý", "Kỷ Sửu", "Canh Dần", "Tân Mão", "Nhâm Thìn", "Quý Tỵ"], ["Ngọ", "Mùi"]),
    (["Giáp Ngọ", "Ất Mùi", "Bính Thân", "Đinh Dậu", "Mậu Tuất", "Kỷ Hợi", "Canh Tý", "Tân Sửu", "Nhâm Dần", "Quý Mão"], ["Thìn", "Tỵ"]),
    (["Giáp Thìn", "Ất Tỵ", "Bính Ngọ", "Đinh Mùi", "Mậu Thân", "Kỷ Dậu", "Canh Tuất", "Tân Hợi", "Nhâm Tý", "Quý Sửu"], ["Dần", "Mão"]),
    (["Giáp Dần", "Ất Mão", "Bính Thìn", "Đinh Tỵ", "Mậu Ngọ", "Kỷ Mùi", "Canh Thân", "Tân Dậu", "Nhâm Tuất", "Quý Hợi"], ["Tý", "Sửu"]),
]

# Âm/Dương của Thiên Can (True=dương, False=âm)
CAN_DUONG = {
    "Giáp": True, "Ất": False, "Bính": True, "Đinh": False, "Mậu": True,
    "Kỷ": False, "Canh": True, "Tân": False, "Nhâm": True, "Quý": False
}

# Ngũ hành của Thiên Can
CAN_NGU_HANH = {
    "Giáp": "Mộc", "Ất": "Mộc",
    "Bính": "Hỏa", "Đinh": "Hỏa",
    "Mậu": "Thổ", "Kỷ": "Thổ",
    "Canh": "Kim", "Tân": "Kim",
    "Nhâm": "Thủy", "Quý": "Thủy"
}

# Ẩn tàng theo 12 Chi (toàn tiếng Việt, thứ tự: chủ khí – thứ khí – mạt khí)
AN_TANG: Dict[str, List[str]] = {
    "Tý":  ["Quý"],
    "Sửu": ["Kỷ","Quý","Tân"],
    "Dần": ["Giáp","Bính","Mậu"],
    "Mão": ["Ất"],
    "Thìn":["Mậu","Ất","Quý"],
    "Tỵ":  ["Bính","Mậu","Canh"],
    "Ngọ": ["Đinh","Kỷ"],
    "Mùi": ["Kỷ","Ất","Đinh"],
    "Thân":["Canh","Nhâm","Mậu"],
    "Dậu": ["Tân"],
    "Tuất":["Mậu","Tân","Đinh"],
    "Hợi":["Nhâm","Giáp"]
}
AN_TANG_TRONG_SO = [1.0, 0.5, 0.3]  # chủ/ thứ/ mạt khí

# Vòng sinh & khắc (ngũ hành)
SINH = {"Mộc":"Hỏa","Hỏa":"Thổ","Thổ":"Kim","Kim":"Thủy","Thủy":"Mộc"}
KHAC = {"Mộc":"Thổ","Thổ":"Thủy","Thủy":"Hỏa","Hỏa":"Kim","Kim":"Mộc"}

def tinh_thai_nguyen(can_thang: str, chi_thang: str) -> Tuple[str, str]:
    """
    Trả về Can Chi của Thai nguyên (lùi 10 tháng so với tháng sinh).
    Dùng vòng 10 Can và vòng 12 Chi của tháng (theo CHI_THANG).
    """
    can_idx = CAN_VI.index(can_thang)
    chi_idx = CHI_THANG.index(chi_thang)
    can_tn = CAN_VI[(can_idx - 9) % 10]
    chi_tn = CHI_THANG[(chi_idx - 9) % 12]
    return can_tn, chi_tn


def tinh_truong_sinh(nhat_chu: str, doi_tuong: str) -> str:
    """
    Trả trạng thái Trường Sinh (theo bảng) của 'doi_tuong' (Chi) với nhật chủ (Can).
    Can dương: chạy thuận chiều Chi. Can âm: chạy ngược chiều Chi.
    Vị trí bắt đầu Trường Sinh của từng Can:
    Giáp: Hợi, Ất: Ngọ, Bính/Mậu: Dần, Đinh/Kỷ: Dậu, Canh: Tỵ, Tân: Tý, Nhâm: Thân, Quý: Mão
    """
    CAN_TS_START = {
        "Giáp": "Hợi", "Ất": "Ngọ",
        "Bính": "Dần", "Mậu": "Dần",
        "Đinh": "Dậu", "Kỷ": "Dậu",
        "Canh": "Tỵ", "Tân": "Tý",
        "Nhâm": "Thân", "Quý": "Mão"
    }
    if nhat_chu not in CAN_TS_START or doi_tuong not in CHI_VI:
        return "N/A"
    start_chi = CAN_TS_START[nhat_chu]
    start_idx = CHI_VI.index(start_chi)
    chi_idx = CHI_VI.index(doi_tuong)
    is_duong = CAN_DUONG.get(nhat_chu, True)
    if is_duong:
        ts_idx = (chi_idx - start_idx) % 12
    else:
        ts_idx = (start_idx - chi_idx) % 12
    return TRUONG_SINH[ts_idx]

def nap_am_luc_thap(can: str, chi: str) -> str:
    """Trả về Nạp Âm của cặp Can Chi (Lục Thập Hoa Giáp)."""
    return NAP_AM_LUC_THAP_HOA_GIAP.get(f"{can} {chi}", "N/A")

def get_khong_vong(can: str, chi: str) -> Optional[str]:
    """Trả về cặp Không Vong của tuần chứa can chi này, hoặc None nếu không xác định."""
    can_chi = f"{can} {chi}"
    for tuan, kv in KHONG_VONG_TUAN:
        if can_chi in tuan:
            return kv
    return None

def is_khong_vong(can: str, chi: str) -> bool:
    """Kiểm tra chi này có thuộc Không Vong của tuần can chi không."""
    kv = get_khong_vong(can, chi)
    if kv is None:
        return False
    return chi in kv

def get_khong_vong_by_ngay(can_ngay: str, chi_ngay: str) -> Optional[List[str]]:
    """Trả về cặp Không Vong của tuần chứa can chi ngày."""
    can_chi_ngay = f"{can_ngay} {chi_ngay}"
    for tuan, kv in KHONG_VONG_TUAN:
        if can_chi_ngay in tuan:
            return kv
    return None

def is_khong_vong_tru(chi_tru: str, can_ngay: str, chi_ngay: str) -> bool:
    """Kiểm tra chi của trụ có thuộc Không Vong của tuần ngày không."""
    kv = get_khong_vong_by_ngay(can_ngay, chi_ngay)
    if kv is None:
        return False
    return chi_tru in kv

# Thập Thần (ten gods) — TIẾNG VIỆT
# QUY TẮC: so sánh ngũ hành giữa Nhật chủ (can ngày) với can khác:
# - Cùng hành: dương–dương hoặc âm–âm => Tỷ Kiên ; khác âm dương => Kiếp Tài
# - Nhật chủ sinh ra (hành của đối tượng = SINH[nhật chủ]):
#     cùng âm dương => Thực Thần ; khác => Thương Quan
# - Nhật chủ khắc (đối tượng là hành mà nhật chủ KHẮC):
#     cùng âm dương => Thiên Tài ; khác => Chính Tài
# - Bị khắc (đối tượng KHẮC nhật chủ):
#     cùng âm dương => Thất Sát ; khác => Chính Quan
# - Được sinh (đối tượng sinh nhật chủ):
#     cùng âm dương => Thiên Ấn ; khác => Chính Ấn
def tinh_thap_than(nhat_chu: str, doi_tuong: str) -> str:
    """Trả tên Thập Thần (tiếng Việt) của 'đối_tượng' so với 'nhật_chu' (đều là THIÊN CAN tiếng Việt)."""
    if nhat_chu not in CAN_NGU_HANH or doi_tuong not in CAN_NGU_HANH:
        return "N/A"
    nh_hanh = CAN_NGU_HANH[nhat_chu]
    dt_hanh = CAN_NGU_HANH[doi_tuong]
    nh_duong = CAN_DUONG[nhat_chu]
    dt_duong = CAN_DUONG[doi_tuong]
    cung_am_duong = (nh_duong == dt_duong)

    if dt_hanh == nh_hanh:
        return "Tỷ Kiên" if cung_am_duong else "Kiếp Tài"
    if dt_hanh == SINH[nh_hanh]:  # nhật chủ sinh ra đối tượng
        return "Thực Thần" if cung_am_duong else "Thương Quan"
    if dt_hanh == KHAC[nh_hanh]:  # nhật chủ khắc đối tượng (tài)
        return "Thiên Tài" if cung_am_duong else "Chính Tài"
    if nh_hanh == KHAC[dt_hanh]:  # đối tượng khắc nhật chủ (quan/sát)
        return "Thất Sát" if cung_am_duong else "Chính Quan"
    if nh_hanh == SINH[dt_hanh]:  # đối tượng sinh nhật chủ (ấn)
        return "Thiên Ấn" if cung_am_duong else "Chính Ấn"
    return "N/A"

# =========================
# QUAN HỆ CHI
# =========================
LUC_XUNG = {("Tý","Ngọ"),("Sửu","Mùi"),("Dần","Thân"),("Mão","Dậu"),("Thìn","Tuất"),("Tỵ","Hợi")}
LUC_HOP  = {("Tý","Sửu"),("Dần","Hợi"),("Mão","Tuất"),("Thìn","Dậu"),("Tỵ","Thân"),("Ngọ","Mùi")}
TAM_HOP = [
    ({"Thân","Tý","Thìn"},"Thủy"),
    ({"Hợi","Mão","Mùi"},"Mộc"),
    ({"Dần","Ngọ","Tuất"},"Hỏa"),
    ({"Tỵ","Dậu","Sửu"},"Kim"),
]
HINH = {("Dần","Tỵ"),("Tỵ","Thân"),("Thân","Dần"),("Sửu","Mùi"),("Mùi","Tuất"),
        ("Tuất","Sửu"),("Tý","Mão"),("Mão","Tý")}
HAI  = {("Tý","Mùi"),("Sửu","Ngọ"),("Dần","Tỵ"),("Mão","Thìn"),("Thân","Hợi"),("Dậu","Tuất")}
PHA  = {("Tý","Dậu"),("Sửu","Thìn"),("Dần","Hợi"),("Mão","Ngọ"),("Thân","Tỵ"),("Mùi","Tuất")}

def cap_trong_tap(a: str, b: str, S: set[Tuple[str,str]]):
    return (a,b) in S or (b,a) in S

def phan_tich_quan_he_chi(chi_4_tru: List[str]) -> Dict:
    rel = {"lục_xung": [],"lục_hợp": [],"tam_hợp": [],"hình": [],"hại": [],"phá": []}
    for i in range(4):
        for j in range(i+1,4):
            a,b = chi_4_tru[i], chi_4_tru[j]
            if cap_trong_tap(a,b, LUC_XUNG): rel["lục_xung"].append([i, j, a+"-"+b])
            if cap_trong_tap(a,b, LUC_HOP):  rel["lục_hợp"].append([i, j, a+"-"+b])
            if cap_trong_tap(a,b, HINH):     rel["hình"].append([i, j, a+"-"+b])
            if cap_trong_tap(a,b, HAI):      rel["hại"].append([i, j, a+"-"+b])
            if cap_trong_tap(a,b, PHA):      rel["phá"].append([i, j, a+"-"+b])
    s = set(chi_4_tru)
    for group, elem in TAM_HOP:
        meet = group.intersection(s)
        if len(meet) >= 2:
            rel["tam_hợp"].append({"nhóm": "-".join(group), "ngũ_hành": elem, "đang_có": "-".join(meet)})
    return rel

# =========================
# TRUE SOLAR TIME (tuỳ chọn)
# =========================
def day_of_year(d: date) -> int:
    return int(d.timetuple().tm_yday)

def equation_of_time_minutes(d: date) -> float:
    N = day_of_year(d)
    B = 2 * math.pi * (N - 81) / 364.0
    return 229.18 * (0.000075 + 0.001868*math.cos(B) - 0.032077*math.sin(B)
                     - 0.014615*math.cos(2*B) - 0.040849*math.sin(2*B))

def true_solar_time(dt_local: datetime, lon: float, tzinfo_obj) -> datetime:
    if dt_local.tzinfo is None:
        dt_local = dt_local.replace(tzinfo=tzinfo_obj)
    utc_offset_min = dt_local.utcoffset().total_seconds() / 60.0
    tz_hours = utc_offset_min / 60.0
    std_meridian = 15.0 * tz_hours
    eot = equation_of_time_minutes(dt_local.date())
    delta_min = 4.0 * (lon - std_meridian) + eot
    return dt_local + timedelta(minutes=delta_min)

# =========================
# TIMEZONE RESOLVER (FALLBACK THÂN THIỆN WINDOWS)
# =========================
def resolve_timezone(tz_str: str):
    # 1) Thử zoneinfo
    if zoneinfo is not None:
        try:
            return zoneinfo.ZoneInfo(tz_str)
        except Exception:
            pass
    # 2) Alias VN
    vn_alias = {"asia/ho_chi_minh", "asia/saigon", "etc/gmt-7", "vietnam", "vn", "utc+7", "gmt+7"}
    if tz_str.lower() in vn_alias:
        return timezone(timedelta(hours=7))
    # 3) Chuỗi "UTC±HH[:MM]" hoặc "GMT±HH[:MM]"
    m = re.fullmatch(r"(?:UTC|GMT)\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?$", tz_str.strip(), re.IGNORECASE)
    if m:
        sign, hh, mm = m.group(1), int(m.group(2)), int(m.group(3) or 0)
        offset = hh + mm/60
        if sign == "-":
            offset = -offset
        return timezone(timedelta(hours=offset))
    # 4) Không nhận ra -> dùng UTC
    print(f"[CẢNH BÁO] Không nhận diện timezone '{tz_str}', tạm dùng UTC.")
    return timezone.utc

# =========================
# CHUYỂN CAN/CHI TỪ LUNAR_PYTHON -> TIẾNG VIỆT
# (lib trả 甲子... nên ta map sang Việt & KHÔNG in chữ Hán)
# =========================
CAN_CN = "甲乙丙丁戊己庚辛壬癸"
ZHI_CN = "子丑寅卯辰巳午未申酉戌亥"
CAN_CN_TO_VI = {c:v for c,v in zip(CAN_CN, CAN_VI)}
ZHI_CN_TO_VI = {c:v for c,v in zip(ZHI_CN, CHI_VI)}

def cn_ganzhi_to_vi_pair(cn: str) -> Tuple[str, str]:
    """'甲子' -> ('Giáp','Tý') ; đảm bảo KHÔNG trả chữ Hán."""
    if not cn or len(cn) < 2:
        return ("","")
    gan = CAN_CN_TO_VI.get(cn[0], "")
    zhi = ZHI_CN_TO_VI.get(cn[1], "")
    return gan, zhi

# =========================
# INPUT / OUTPUT MODEL (CLI)
# =========================
@dataclass
class InputArgs:
    dt: datetime
    tz: str
    gender: str
    method: str
    lon: Optional[float] = None
    print_json: bool = False

# =========================
# TIỆN ÍCH: TIẾN CAN/CHI & LƯU NIÊN
# =========================
def tien_can_chi_vi(can_vi: str, chi_vi: str, step: int = 1) -> Tuple[str, str]:
    """
    Tiến 'step' bước theo lục thập hoa giáp từ (can_vi, chi_vi).
    step có thể âm (thoái).
    """
    if can_vi not in CAN_VI or chi_vi not in CHI_VI:
        return ("", "")
    ci = CAN_VI.index(can_vi)
    zi = CHI_VI.index(chi_vi)
    can2 = CAN_VI[(ci + step) % 10]
    chi2 = CHI_VI[(zi + step) % 12]
    return can2, chi2


def build_luu_nien(y_gan_vi: str, y_zhi_vi: str, birth_year: int, years: int = 100) -> List[Dict]:
    """
    Tạo danh sách Lưu niên từ năm sinh (tuổi 0) đến 'years' năm sau (tuổi 'years').
    Mỗi mục gồm: năm_dương, tuổi, can_chi, nạp_âm.
    *Can Chi năm k được lấy bằng cách tiến k bước từ Can Chi năm sinh.*
    """
    out = []
    can, chi = y_gan_vi, y_zhi_vi
    for k in range(0, years + 1):  # tuổi 0..years
        can_k, chi_k = (can, chi) if k == 0 else tien_can_chi_vi(y_gan_vi, y_zhi_vi, k)
        out.append({
            "năm_dương": birth_year + k,
            "tuổi": k,
            "can_chi": f"{can_k} {chi_k}",
            "nạp_âm": nap_am_luc_thap(can_k, chi_k)
        })
    return out

# =========================
# TÍNH BÁT TỰ LOCAL
# =========================
def compute_bazi_local(args: InputArgs) -> Dict:
    tzinfo_obj = resolve_timezone(args.tz)
    base_local_dt = args.dt.astimezone(tzinfo_obj)

    if args.method == "true_solar_time":
        if args.lon is None:
            raise ValueError("Thiếu --lon (kinh độ) cho true_solar_time")
        local_dt = true_solar_time(base_local_dt, args.lon, tzinfo_obj)
        time_basis = "Giờ Mặt Trời thật"
    else:
        local_dt = base_local_dt
        time_basis = "Giờ chuẩn múi"

    # Lấy Bát tự từ lunar_python
    solar = Solar.fromYmdHms(local_dt.year, local_dt.month, local_dt.day,
                             local_dt.hour, local_dt.minute, local_dt.second)
    lunar = solar.getLunar()
    bz = lunar.getEightChar()

    # Can/Chi 4 trụ (đã map sang VI)
    y_gan, y_zhi = cn_ganzhi_to_vi_pair(bz.getYear())
    m_gan, m_zhi = cn_ganzhi_to_vi_pair(bz.getMonth())
    d_gan, d_zhi = cn_ganzhi_to_vi_pair(bz.getDay())   # Nhật chủ = d_gan
    h_gan, h_zhi = cn_ganzhi_to_vi_pair(bz.getTime())

    if not all([y_gan, m_gan, d_gan, h_gan, y_zhi, m_zhi, d_zhi, h_zhi]):
        raise ValueError("Không chuyển đổi được Can/Chi sang tiếng Việt.")

    # Ngũ hành theo Can/Chi (in tiếng Việt)
    def ngu_hanh_gc(gan: str, zhi: str) -> str:
        # Ở đây dùng Ngũ hành theo Can là chính (đơn giản/nhất quán)
        return CAN_NGU_HANH[gan]

    # Thập Thần theo CAN của 4 trụ (so với Nhật chủ = d_gan)
    ss_year  = tinh_thap_than(d_gan, y_gan)
    ss_month = tinh_thap_than(d_gan, m_gan)
    ss_day   = "Nhật chủ"
    ss_hour  = tinh_thap_than(d_gan, h_gan)

    # Ẩn tàng (phó tinh) + Thập Thần theo Nhật chủ
    def build_an_tang(chi: str) -> List[Dict[str,str]]:
        lst = AN_TANG.get(chi, [])
        out = []
        for idx, gan in enumerate(lst):
            vai_tro = ["chủ khí","thứ khí","mạt khí"][min(idx,2)]
            thap_than = tinh_thap_than(d_gan, gan)
            out.append({"can": gan, "vai_tro": vai_tro, "thập_thần_so_với_nhật_chủ": thap_than})
        return out

    an_y = build_an_tang(y_zhi)
    an_m = build_an_tang(m_zhi)
    an_d = build_an_tang(d_zhi)
    an_h = build_an_tang(h_zhi)
    # Gói 4 trụ
    tru = {
        "năm":   {"can": y_gan, "chi": y_zhi, "ngũ_hành_can": ngu_hanh_gc(y_gan, y_zhi), "thập_thần_theo_can": ss_year,
                  "ẩn_tàng": an_y, "trường_sinh": tinh_truong_sinh(d_gan, y_zhi), "nạp_âm": nap_am_luc_thap(y_gan, y_zhi),
                  "không_vong": is_khong_vong_tru(y_zhi, d_gan, d_zhi)},
        "tháng": {"can": m_gan, "chi": m_zhi, "ngũ_hành_can": ngu_hanh_gc(m_gan, m_zhi), "thập_thần_theo_can": ss_month,
                  "ẩn_tàng": an_m, "trường_sinh": tinh_truong_sinh(d_gan, m_zhi), "nạp_âm": nap_am_luc_thap(m_gan, m_zhi),
                  "không_vong": is_khong_vong_tru(m_zhi, d_gan, d_zhi)},
        "ngày":  {"can": d_gan, "chi": d_zhi, "ngũ_hành_can": ngu_hanh_gc(d_gan, d_zhi), "thập_thần_theo_can": ss_day,
                  "ẩn_tàng": an_d, "trường_sinh": tinh_truong_sinh(d_gan, d_zhi), "nạp_âm": nap_am_luc_thap(d_gan, d_zhi),
                  "không_vong": is_khong_vong_tru(d_zhi, d_gan, d_zhi)},
        "giờ":   {"can": h_gan, "chi": h_zhi, "ngũ_hành_can": ngu_hanh_gc(h_gan, h_zhi), "thập_thần_theo_can": ss_hour,
                  "ẩn_tàng": an_h, "trường_sinh": tinh_truong_sinh(d_gan, h_zhi), "nạp_âm": nap_am_luc_thap(h_gan, h_zhi),
                  "không_vong": is_khong_vong_tru(h_zhi, d_gan, d_zhi)},
    }

    # Điểm Ngũ hành có trọng số (can bộc lộ + ẩn tàng)
    diem = {"Kim":0.0,"Mộc":0.0,"Thủy":0.0,"Hỏa":0.0,"Thổ":0.0}
    for key in ["năm","tháng","ngày","giờ"]:
        g = tru[key]["can"]
        diem[CAN_NGU_HANH[g]] += 1.0
        for idx, item in enumerate(tru[key]["ẩn_tàng"]):
            w = AN_TANG_TRONG_SO[min(idx,2)]
            diem[CAN_NGU_HANH[item["can"]]] += w

    # Quan hệ chi
    relations = phan_tich_quan_he_chi([tru[k]["chi"] for k in ["năm","tháng","ngày","giờ"]])

    # Đại vận (giữ nguyên tính toán từ lib, in tiếng Việt)
    sex = 1 if args.gender.upper()=="M" else 0
    yun = bz.getYun(sex)
    try:
        start = yun.getStartSolar()
        ngay_khoi_van = start.toYmd()
    except Exception:
        ngay_khoi_van = None

    # sex: 1 = Nam, 0 = Nữ (đã có từ trên)
    is_year_duong = CAN_DUONG.get(y_gan, True)  # True = Dương, False = Âm

    # Quy tắc: Dương Nam / Âm Nữ => tiến (+1); Âm Nam / Dương Nữ => lùi (-1)
    if (is_year_duong and sex == 1) or ((not is_year_duong) and sex == 0):
        daivan_direction = 1
    else:
        daivan_direction = -1

    # --- SỬA 1: thu thập đại vận, BỎ i=0 (nếu có), SAU ĐÓ bù đến đủ 10 ---
    dai_van = []
    raw_list = list(yun.getDaYun())  # lib có thể trả 9 mục (i=0..8)

    # gom các mục i>0 như code cũ (nhiều lib i=0 là tiền vận)
    tmp_items = []
    for i, dy in enumerate(raw_list):
        try:
            gz = dy.getGanZhi()  # chuỗi Hán
            if isinstance(gz, str) and len(gz) >= 2:
                gan_vi = CAN_CN_TO_VI.get(gz[0], "")
                zhi_vi = ZHI_CN_TO_VI.get(gz[1], "")
                can_chi_vi = f"{gan_vi} {zhi_vi}" if gan_vi and zhi_vi else ""
            else:
                gan = getattr(dy, "getGan", lambda: None)()
                zhi = getattr(dy, "getZhi", lambda: None)()
                gan_vi = CAN_CN_TO_VI.get(gan, "") if isinstance(gan, str) and len(gan)==1 else ""
                zhi_vi = ZHI_CN_TO_VI.get(zhi, "") if isinstance(zhi, str) and len(zhi)==1 else ""
                can_chi_vi = f"{gan_vi} {zhi_vi}" if gan_vi and zhi_vi else ""
        except Exception:
            can_chi_vi = ""

        if i > 0:  # giữ nguyên quy tắc lọc i=0
            tmp_items.append({
                "start_year": dy.getStartYear(),
                "start_age":  dy.getStartAge(),
                "gan_vi": gan_vi if 'gan_vi' in locals() else "",
                "zhi_vi": zhi_vi if 'zhi_vi' in locals() else "",
                "can_chi_vi": can_chi_vi
            })

    # cắt còn tối đa 10 nếu lib trả nhiều
    tmp_items = tmp_items[:10]

    # nếu thiếu thì tự nội suy thêm cho đủ 10
    while len(tmp_items) < 10 and len(tmp_items) > 0:
        prev = tmp_items[-1]
        prev_year = prev["start_year"]
        prev_age  = prev["start_age"]
        prev_gan  = prev["gan_vi"]
        prev_zhi  = prev["zhi_vi"]

        gan2, zhi2 = tien_can_chi_vi(prev_gan, prev_zhi, daivan_direction)
        tmp_items.append({
            "start_year": (prev_year + 10) if isinstance(prev_year, int) else None,
            "start_age":  (prev_age + 10) if isinstance(prev_age, int) else None,
            "gan_vi": gan2,
            "zhi_vi": zhi2,
            "can_chi_vi": f"{gan2} {zhi2}" if gan2 and zhi2 else ""
        })

    # đánh lại thứ_tự 0..9 (tùy bạn muốn 0-based hay 1-based; ở đây 0..9)
    for idx, it in enumerate(tmp_items):
        dai_van.append({
            "thứ_tự": idx,
            "bắt_đầu_năm_dương": it["start_year"],
            "bắt_đầu_tuổi": it["start_age"],
            "can_chi": it["can_chi_vi"]
        })

    luu_nien = build_luu_nien(y_gan, y_zhi, local_dt.year, years=99)
    can_cung_menh, chi_cung_menh = tinh_cung_menh_full(y_gan, m_zhi, h_zhi)
    can_thai_nguyen, chi_thai_nguyen = tinh_thai_nguyen(m_gan, m_zhi)
    return {
        "đầu_vào": {
            "thời_điểm_nhập": base_local_dt.isoformat(),
            "thời_điểm_tính": local_dt.isoformat(),
            "múi_giờ": args.tz,
            "cơ_sở_thời_gian": time_basis,
            "kinh_độ": args.lon,
            "giới_tính": "Nam" if sex==1 else "Nữ"
        },
        "trụ": tru,
        "điểm_ngũ_hành": diem,
        "quan_hệ_chi": relations,
        "đại_vận": {
            "khởi_vận_sau": {"năm": yun.getStartYear(), "tháng": yun.getStartMonth(), "ngày": yun.getStartDay()},
            "ngày_dương_khởi_vận": ngay_khoi_van,
            "các_chu_kỳ": dai_van,
        },
        "lưu_niên": luu_nien,
        "cung_menh": {"can": can_cung_menh, "chi": chi_cung_menh},
        "thai_nguyen": {"can": can_thai_nguyen, "chi": chi_thai_nguyen}
    }

# =========================
# IN RA TERMINAL (TÓM TẮT DỄ ĐỌC)
# =========================
def print_summary(result: Dict):
    print("\n=== TÓM TẮT BÁT TỰ (TIẾNG VIỆT) ===")
    inp = result["đầu_vào"]
    print(f"- Thời điểm nhập: {inp['thời_điểm_nhập']}")
    print(f"- Thời điểm tính: {inp['thời_điểm_tính']}")
    print(f"- Cơ sở thời gian: {inp['cơ_sở_thời_gian']}")
    print(f"- Giới tính: {inp['giới_tính']}")

    print("\n[4 TRỤ]")
    thutu = [("năm","Năm"),("tháng","Tháng"),("ngày","Ngày"),("giờ","Giờ")]
    for key,label in thutu:
        p = result["trụ"][key]
        print(f"- {label}: {p['can']} {p['chi']} | Ngũ hành (Can): {p['ngũ_hành_can']} | Thập Thần (theo Can): {p['thập_thần_theo_can']}")
        print(f"  · Trường sinh: {p['trường_sinh']}")
        print(f"  · Nạp âm: {p['nạp_âm']}")
        print(f"  · Không vong: {'Có' if p['không_vong'] else 'Không'}")
        if p["ẩn_tàng"]:
            ds = ", ".join([f"{x['can']} ({x['vai_tro']}, {x['thập_thần_so_với_nhật_chủ']})" for x in p["ẩn_tàng"]])
            print(f"  · Ẩn tàng: {ds}")

    print("\n[ĐIỂM NGŨ HÀNH (có trọng số Can + Ẩn tàng)]")
    sc = result["điểm_ngũ_hành"]
    print("  Kim: %.2f | Mộc: %.2f | Thủy: %.2f | Hỏa: %.2f | Thổ: %.2f" % (sc["Kim"], sc["Mộc"], sc["Thủy"], sc["Hỏa"], sc["Thổ"]))

    print("\n[QUAN HỆ CHI]")
    rel = result["quan_hệ_chi"]
    def show_pairs(name):
        arr = rel[name]
        return "(trống)" if not arr else "; ".join([f"{['Năm','Tháng','Ngày','Giờ'][i]}-{['Năm','Tháng','Ngày','Giờ'][j]}:{s}" for i,j,s in arr])
    print("  Lục xung:", show_pairs("lục_xung"))
    print("  Lục hợp:", show_pairs("lục_hợp"))
    if rel["tam_hợp"]:
        print("  Tam hợp:", "; ".join([f"Nhóm {x['nhóm']} ({x['ngũ_hành']}) gặp: {x['đang_có']}" for x in rel["tam_hợp"]]))
    else:
        print("  Tam hợp: (trống)")
    print("  Hình:", show_pairs("hình"))
    print("  Hại:", show_pairs("hại"))
    print("  Phá:", show_pairs("phá"))

    print("\n[ĐẠI VẬN]")
    dv = result["đại_vận"]
    kv = dv["khởi_vận_sau"]
    print(f"  Khởi vận sau: {kv['năm']} năm {kv['tháng']} tháng {kv['ngày']} ngày")
    print(f"  Ngày dương khởi vận: {dv['ngày_dương_khởi_vận']}")
    for r in dv["các_chu_kỳ"]:
        print(f"  · #{r['thứ_tự']:02d}: Bắt đầu {r['bắt_đầu_năm_dương']} (tuổi {r['bắt_đầu_tuổi']}), can chi: {r['can_chi']}")

    print("\n[LƯU NIÊN] (tuổi 0..60)")
    ln = result.get("lưu_niên", [])
    # In gọn 0..10 tuổi đầu làm mẫu, tránh quá dài
    for r in ln[:11]:
        print(f"  · Năm {r['năm_dương']}: tuổi {r['tuổi']}, {r['can_chi']} — {r['nạp_âm']}")
    if len(ln) > 11:
        print(f"  ... ({len(ln)-11} mục nữa, xem đầy đủ bằng --print-json)")

    # ...existing code in print_summary...
    print("\n[CUNG MỆNH]")
    cm = result.get("cung_menh", {})
    print(f"  Can: {cm.get('can','N/A')}, Chi: {cm.get('chi','N/A')}")

    print("\n[THAI NGUYÊN]")
    tn = result.get("thai_nguyen", {})
    print(f"  Can: {tn.get('can','N/A')}, Chi: {tn.get('chi','N/A')}")
# ...existing code...
# =========================
# CLI
# =========================
def parse_args() -> InputArgs:
    parser = argparse.ArgumentParser(
        description="Bát tự CLI (thuần tiếng Việt + Ẩn tàng + Thập Thần). Ví dụ:\n"
                    "python bazi.py --dt 2002-10-06T05:30:00 --tz UTC+7 --gender F --method standard",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--dt", required=True, help="Thời điểm local (ISO 8601), vd: 2002-10-06T05:30:00")
    parser.add_argument("--tz", default="UTC+7", help="Timezone: IANA hoặc chuỗi như UTC+7, Asia/Ho_Chi_Minh (có fallback)")
    parser.add_argument("--gender", choices=["M","F","m","f"], default="M", help="Giới tính: M/F. Mặc định M")
    parser.add_argument("--method", choices=["standard","true_solar_time"], default="standard", help="Chuẩn múi hoặc Giờ Mặt Trời thật")
    parser.add_argument("--lon", type=float, default=None, help="Kinh độ (độ, Đông +). Bắt buộc khi true_solar_time")
    parser.add_argument("--print-json", action="store_true", help="In thêm JSON đầy đủ")
    a = parser.parse_args()
    try:
        dt = datetime.fromisoformat(a.dt)
    except Exception:
        raise SystemExit("❌ --dt không đúng ISO 8601. Ví dụ hợp lệ: 2002-10-06T05:30:00")
    return InputArgs(dt=dt, tz=a.tz, gender=a.gender, method=a.method, lon=a.lon, print_json=a.print_json)

if __name__ == "__main__":
    args = parse_args()
    try:
        kq = compute_bazi_local(args)
    except Exception as e:
        print("❌ Lỗi:", e)
        raise SystemExit(1)
    print_summary(kq)
    if args.print_json:
        print("\n=== JSON ===")
        print(json.dumps(kq, ensure_ascii=False, indent=2))

