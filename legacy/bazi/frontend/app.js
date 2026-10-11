// =================== CẤU HÌNH & TIỆN ÍCH ===================

// URL API backend FastAPI (nhớ chạy uvicorn ở 127.0.0.1:8000)
const API_URL = "http://127.0.0.1:8000/api/bazi";

// Helper lấy nhanh element theo selector
const $ = (s, r=document) => r.querySelector(s);

// Map class màu theo ngũ hành (tên class CSS ở style.css)
const ELEM = { wood:'el-wood', fire:'el-fire', earth:'el-earth', metal:'el-metal', water:'el-water' };

// Map Can → Ngũ hành
const canElem = {
  'Giáp':'wood','Ất':'wood','Bính':'fire','Đinh':'fire',
  'Mậu':'earth','Kỷ':'earth','Canh':'metal','Tân':'metal',
  'Nhâm':'water','Quý':'water'
};

// Map Chi → Ngũ hành
const chiElem = {
  'Tý':'water','Sửu':'earth','Dần':'wood','Mão':'wood',
  'Thìn':'earth','Tỵ':'fire','Ngọ':'fire','Mùi':'earth',
  'Thân':'metal','Dậu':'metal','Tuất':'earth','Hợi':'water'
};

// Escape HTML để tránh lỗi XSS khi hiển thị text
const esc = s => String(s ?? "").replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

// Tạo nhanh 1 <td> với HTML con
const td = h => `<td>${h}</td>`;

// Rút gọn tên Thập thần cho gọn cột (ví dụ "Thiên Tài" → "T.Tài")
const sg = t => t?.includes("Thực")?"Thực":
               t?.includes("Thương")?"Thương":
               t?.includes("Thiên Tài")?"T.Tài":
               t?.includes("Tài")?"Tài":
               t?.includes("Chính Quan")?"Quan":
               t?.includes("Sát")?"Sát":
               t?.includes("Ấn")?"Ấn":
               t?.includes("Kiêu")?"Kiêu":
               t?.includes("Tỉ")?"Tỉ":
               t?.includes("Kiếp")?"Kiếp":(t||"");

// =================== LẤY ELEMENT ĐÍCH ===================
const form = $('#bazi-form');             // Form nhập liệu
const errBox = $('#error');               // Khung lỗi
const result = $('#result');              // Khối kết quả (ẩn/hiện)
const pillarsBody = $('#pillars-body');   // <tbody> của bảng trụ
const luckWrap = $('#luck');              // Container Đại vận
const luuNienWrap = $('#luunien');        // Container Lưu niên
const menhCungWrap = $('#menhcung');      // Container Mệnh cung
const thaiNguyenWrap = $('#thainguyen');  // Container Thai nguyên
const rName = $('#rName'), rGender = $('#rGender'), rISO = $('#rISO'), rTZ = $('#rTZ'); // Text info

// =================== RENDER BẢNG TỨ TRỤ ===================
function renderPillars(data){
  const ps = [data.trụ.năm, data.trụ.tháng, data.trụ.ngày, data.trụ.giờ];

  // 1) CHỦ TINH
  const row1 = `<tr><td class="td-left">CHỦ TINH</td>${
    ps.map(p => td(esc(p.thập_thần_theo_can||'-'))).join('')
  }</tr>`;

  // 2) BÁT TỰ (Can/Chi)
  const row2 = `<tr><td class="td-left">BÁT TỰ</td>${
    ps.map(p => {
      const canCls = ELEM[canElem[p.can]] || '';
      const chiCls = ELEM[chiElem[p.chi]] || '';
      return td(
        `<div class="cell">
           <span class="badge pillar ${canCls}">${esc(p.can)}</span>
           <span class="badge pillar ${chiCls}">${esc(p.chi)}</span>
         </div>`
      );
    }).join('')
  }</tr>`;

  // 3) TÀNG ẨN
  const row3 = `<tr><td class="td-left">TÀNG ẨN</td>${
    ps.map(p => {
      const hidden = (p.ẩn_tàng||[]).map(x =>
        `<span class="badge ${ELEM[canElem[x.can]]||''}">${esc(x.can)}</span>`
      ).join('');
      return td(`<div class="badges">${hidden||''}</div>`);
    }).join('')
  }</tr>`;

  // 4) PHÓ TINH
  const row4 = `<tr><td class="td-left">PHÓ TINH</td>${
    ps.map(p => {
      const deputy = (p.ẩn_tàng||[])
        .map(x => sg(x.thập_thần_so_với_nhật_chủ))
        .filter(Boolean).join(' · ');
      return td(esc(deputy || '-'));
    }).join('')
  }</tr>`;

  // 5) Trường sinh
  const row5 = `<tr><td class="td-left">Trường sinh</td>${
    ps.map(p => td(esc(p.trường_sinh||''))).join('')
  }</tr>`;

  // 6) Nạp âm
  const row6 = `<tr><td class="td-left">Nạp âm</td>${
    ps.map(p => td(esc(p.nạp_âm||''))).join('')
  }</tr>`;

  // ====== 7) ĐẠI VẬN – 1 hàng, trái là nhãn, phải colspan=4 ======
  const dvList = (data.đại_vận?.các_chu_kỳ || []).slice(0,10);
  const dvHTML = dvList.map(dv=>{
    const [can, chi] = String(dv.can_chi||'').trim().split(/\s+/);
    const canCls = ELEM[canElem[can]]||'', chiCls = ELEM[chiElem[chi]]||'';
    return `<div class="cycle">
      <div class="dv">
        <span class="dv-part ${canCls}">${esc(can||'')}</span>
        <span class="dv-part ${chiCls}">${esc(chi||'')}</span>
      </div>
      <div class="dv-year">${esc(dv.bắt_đầu_năm_dương||'')}</div>
    </div>`;
  }).join('');
  const rowDV = `<tr>
    <td class="td-left">ĐẠI VẬN</td>
    <td class="td-block" colspan="4"><div class="inner"><div class="luck">${dvHTML}</div></div></td>
  </tr>`;

// ====== 8) LƯU NIÊN – 1 hàng (nếu nhiều sẽ tự xuống dòng trong grid) ======
    // ====== LƯU NIÊN ======
    const lnList = data.lưu_niên || data.luu_nien || [];
    const lnHTML = lnList.map(ln => {
    const [can, chi] = String(ln.can_chi || "").trim().split(/\s+/);
    const canCls = ELEM[canElem[can]] || "";
    const chiCls = ELEM[chiElem[chi]] || "";
    const yearText = esc(ln.năm_dương || ln.nam_duong || "");

    return `
        <div class="year" title="${esc(ln.nạp_âm || ln.nap_am || '')}">
        <div class="gz-vertical">
            <span class="can dv-part ${canCls}">${esc(can || "")}</span>
            <span class="chi dv-part ${chiCls}">${esc(chi || "")}</span>
        </div>
        <div class="dv-year">${yearText}</div>
        </div>
    `;
    }).join("");

    const rowLN = `<tr>
    <td class="td-left">LƯU NIÊN</td>
    <td class="td-block" colspan="4">
        <div class="inner"><div class="luunien">${lnHTML}</div></div>
    </td>
    </tr>`;


  // ====== 9) MỆNH CUNG – 1 hàng, panel 2 cột ======
  const mc = data.mệnh_cung || data.menh_cung || {};
  const mcCanCls = ELEM[canElem[mc.can]]||'', mcChiCls = ELEM[chiElem[mc.chi]]||'';
  const rowMC = `<tr>
    <td class="td-left">MỆNH CUNG</td>
    <td class="td-block" colspan="4">
      <div class="inner">
        <div class="panel mc-2cols">
          <div class="item">
            <div class="label">Can Chi</div>
            <div class="value"><span class="${mcCanCls}">${esc(mc.can||'')}</span> · <span class="${mcChiCls}">${esc(mc.chi||'')}</span></div>
          </div>
          <div class="item">
            <div class="label">Ghi chú</div>
            <div class="value">${esc(mc.ghi_chu || mc.note || '—')}</div>
          </div>
        </div>
      </div>
    </td>
  </tr>`;

  // ====== 10) THAI NGUYÊN – 1 hàng, panel 4 cột ======
  const tn = data.thai_nguyên || data.thai_nguyen_info || {};
  const tnItems = [
    ["NIÊN THÂN",  tn.niên_thân  || tn.nien_than],
    ["NGUYỆT THÂN",tn.nguyệt_thân|| tn.nguyet_than],
    ["NHẬT THÂN",  tn.nhật_thân  || tn.nhat_than],
    ["THỜI THÂN",  tn.thời_thân  || tn.thoi_than],
  ].map(([label,val])=>`
    <div class="item">
      <div class="label">${label}</div>
      <div class="value">${esc(val||'—')}</div>
    </div>`).join('');
  const rowTN = `<tr>
    <td class="td-left">THAI NGUYÊN</td>
    <td class="td-block" colspan="4">
      <div class="inner"><div class="panel tn-4cols">${tnItems}</div></div>
    </td>
  </tr>`;

  // Gắn tất cả vào tbody
  pillarsBody.innerHTML = row1 + row2 + row3 + row4 + row5 + row6 + rowDV + rowLN + rowMC + rowTN;
}


// =================== RENDER ĐẠI VẬN (10 ô / 1 hàng) ===================
function renderLuck(data){
  // Lấy danh sách chu kỳ đại vận; cắt đúng 10 phần tử đầu
  const list = (data.đại_vận?.các_chu_kỳ || []).slice(0, 10);

  // Tạo HTML cho mỗi ô: 2 dòng (Can trên, Chi dưới) + năm bắt đầu
  luckWrap.innerHTML = list.map(dv => {
    const cc = String(dv.can_chi || "").trim();           // "Canh Tuất" ...
    const [can, chi] = cc.split(/\s+/);                   // Tách thành 2 phần
    const canCls = ELEM[canElem[can]] || "";              // Màu can
    const chiCls = ELEM[chiElem[chi]] || "";              // Màu chi
    return `
      <div class="cycle">
        <div class="dv">
          <span class="dv-part ${canCls}">${esc(can || "")}</span>
          <span class="dv-part ${chiCls}">${esc(chi || "")}</span>
        </div>
        <div class="dv-year">${esc(dv.bắt_đầu_năm_dương || "")}</div>
      </div>
    `;
  }).join("");
}

// =================== RENDER LƯU NIÊN ===================
function renderLuuNien(data){
  const list = data.lưu_niên || data.luu_nien || [];
  luuNienWrap.innerHTML = list.map(ln => {
    const [can, chi] = String(ln.can_chi || "").trim().split(/\s+/);
    const canCls = ELEM[canElem[can]] || "";
    const chiCls = ELEM[chiElem[chi]] || "";
    const yearText = esc(ln.năm_dương || ln.nam_duong || "");
    const ageText  = (ln.tuổi ?? ln.tuoi) !== undefined ? ` · ${esc(ln.tuổi ?? ln.tuoi)}` : "";
    return `
      <div class="year">
        <div class="dv" style="gap:2px">
          <span class="dv-part ${canCls}" style="font-weight:600;font-size:14px">${esc(can||"")}</span>
          <span class="dv-part ${chiCls}" style="font-weight:600;font-size:14px">${esc(chi||"")}</span>
        </div>
        <div class="dv-year">${yearText}${ageText}</div>
      </div>`;
  }).join("");
}


// =================== RENDER MỆNH CUNG ===================
function renderMenhCung(data){
  const mc = data.mệnh_cung || data.menh_cung;
  if(!mc){ // Nếu backend chưa trả
    menhCungWrap.innerHTML = `<div class="item"><div class="value">—</div></div>`;
    return;
  }
  // Xác định màu theo can/chi
  const canCls = ELEM[canElem[mc.can]] || "";
  const chiCls = ELEM[chiElem[mc.chi]] || "";
  // Gắn 2 ô: Can-Chi và Ghi chú
  menhCungWrap.innerHTML = `
    <div class="item">
      <div class="label">Can Chi</div>
      <div class="value"><span class="${canCls}">${esc(mc.can||'')}</span> · <span class="${chiCls}">${esc(mc.chi||'')}</span></div>
    </div>
    <div class="item">
      <div class="label">Ghi chú</div>
      <div class="value">${esc(mc.ghi_chu || mc.note || "—")}</div>
    </div>
  `;
}

// =================== RENDER THAI NGUYÊN ===================
function renderThaiNguyen(data){
  const tn = data.thai_nguyên || data.thai_nguyen_info || {};
  // Mảng 4 ô theo thứ tự như ảnh
  const items = [
    ["NIÊN THÂN",  tn.niên_thân  || tn.nien_than],
    ["NGUYỆT THÂN",tn.nguyệt_thân|| tn.nguyet_than],
    ["NHẬT THÂN",  tn.nhật_thân  || tn.nhat_than],
    ["THỜI THÂN",  tn.thời_thân  || tn.thoi_than],
  ];
  // Render 4 item; nếu thiếu thì hiển thị "—"
  thaiNguyenWrap.innerHTML = items.map(([label, val]) => `
    <div class="item">
      <div class="label">${label}</div>
      <div class="value">${esc(val || "—")}</div>
    </div>
  `).join("");
}

// =================== XỬ LÝ SUBMIT FORM ===================
form.addEventListener("submit", async (e) => {
  e.preventDefault();                    // Chặn submit mặc định (reload trang)
  errBox.hidden = true; errBox.textContent = ""; // Ẩn thông báo lỗi cũ

  // Lấy dữ liệu từ form
  const name   = $("#name").value.trim();
  const d      = String($("#day").value).padStart(2,'0');
  const m      = String($("#month").value).padStart(2,'0');
  const y      = $("#year").value;
  const hh     = String($("#hour").value).padStart(2,'0');
  const mm     = String($("#minute").value).padStart(2,'0');
  const gender = $("#gender").value;
  const tz     = $("#tz").value;

  // Kiểm tra năm nhanh để tránh gửi dữ liệu rỗng
  if(!y || +y<1900 || +y>2100){
    errBox.textContent = "Năm không hợp lệ";
    errBox.hidden = false;
    return;
  }

  // Ghép thành ISO-8601 cho backend (YYYY-MM-DDTHH:MM:SS)
  const iso = `${y}-${m}-${d}T${hh}:${mm}:00`;

  // Disable nút để tránh double-click
  $("#btnSubmit").disabled = true;

  try{
    // Gọi API FastAPI
    const res = await fetch(API_URL, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ dt: iso, tz, gender, method: "standard" }) // Body theo schemas backend
    });

    // Parse JSON
    const json = await res.json();

    // Nếu backend trả { ok: false, error: "..." }
    if(!json.ok) throw new Error(json.error || "Lỗi không xác định");

    // Đổ thông tin tóm tắt
    rName.textContent   = name || "Ẩn danh";
    rGender.textContent = (gender === "M") ? "Nam" : "Nữ";
    rISO.textContent    = iso;
    rTZ.textContent     = tz;

    // Xóa nội dung cũ (nếu có) trước khi render mới
    pillarsBody.innerHTML = "";

    // Render tất cả phần
    renderPillars(json.data);
    // Hiện khối kết quả + cuộn tới đó
    result.hidden = false;
    result.scrollIntoView({behavior:"smooth"});
  }catch(err){
    // Hiện thông báo lỗi ra UI
    errBox.textContent = String(err.message || err);
    errBox.hidden = false;
  }finally{
    // Mở khóa nút submit dù thành công hay lỗi
    $("#btnSubmit").disabled = false;
  }
});

// =================== NÚT RESET ===================
$("#btnReset")?.addEventListener("click", () => {
    result.hidden = true;
    pillarsBody.innerHTML = "";
    errBox.hidden = true; errBox.textContent = "";
    form.reset();

});
