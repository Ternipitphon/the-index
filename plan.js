// ══════════════════════════════════════════════════════════════════
// plan.js — หน้าแผนการปลูก (ดึงข้อมูลจาก result.html ที่บันทึกไว้ใน localStorage
// แล้วส่งให้ backend Gemini สร้างแผนการปลูกแบบละเอียด)
// ══════════════════════════════════════════════════════════════════

// ── ตั้งค่า API Base: ยิงไป Backend Chat.py (endpoint /api/plan รวมอยู่ในตัวเดียวกับ /chat และ /api/analyze) ──
// หมายเหตุ: Chat.py รันที่พอร์ต 5000 ทั้งหมด (ไม่มีพอร์ตแยกต่างหากสำหรับ plan อีกต่อไป)
const PLAN_API_PORT = 5000;
const PLAN_API_PROD_URL = 'https://the-index-d3hd.onrender.com'; // backend จริงบน Render (เหมือนที่ Chatai.js ใช้)
const API_BASE = (
  window.location.hostname === 'localhost' ||
  window.location.hostname === '127.0.0.1'
) ? `http://localhost:${PLAN_API_PORT}` : PLAN_API_PROD_URL;

const USAGE_KEY = 'agrifuture_usage';

let currentUserEmail = 'anonymous';
let selectedSession = null; // session ที่ผู้ใช้เลือกจาก picker (มี inputs + result)
let pickerChoiceIndex = null; // index ที่กำลังเลือกอยู่ใน modal ก่อนกดยืนยัน

// ── Elements ──────────────────────────────────────────────────────
const openPickerBtn = document.getElementById('openPickerBtn');
const closePickerBtn = document.getElementById('closePickerBtn');
const pickerOverlay = document.getElementById('pickerOverlay');
const pickerBody = document.getElementById('pickerBody');
const pickerCount = document.getElementById('pickerCount');
const confirmAddBtn = document.getElementById('confirmAddBtn');

const emptyStateSection = document.getElementById('emptyStateSection');
const selectedSection = document.getElementById('selectedSection');
const selectedCropCard = document.getElementById('selectedCropCard');
const clearSelectedBtn = document.getElementById('clearSelectedBtn');
const selectedMiniList = document.getElementById('selectedMiniList');

const planBtn = document.getElementById('planBtn');
const planLoadingSection = document.getElementById('planLoadingSection');
const planErrorSection = document.getElementById('planErrorSection');
const planErrorMsg = document.getElementById('planErrorMsg');
const planResultSection = document.getElementById('planResultSection');

const toast = document.getElementById('toast');
const toastMsg = document.getElementById('toastMsg');

const sidebar = document.getElementById('sidebar');
const sidebarToggle = document.getElementById('sidebarToggle');

// ── Sidebar toggle (มือถือ) ──────────────────────────────────────
if (sidebarToggle) {
  sidebarToggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
  });
}

// ── Toast helper ──────────────────────────────────────────────────
let toastTimer = null;
function showToast(msg) {
  toastMsg.textContent = msg;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 2600);
}

// ── โหลด session ทั้งหมดของผู้ใช้ปัจจุบันจาก localStorage ──────────
function loadUserSessions() {
  try {
    const all = JSON.parse(localStorage.getItem(USAGE_KEY) || '{}');
    const bucket = all[currentUserEmail];
    return (bucket && Array.isArray(bucket.sessions)) ? bucket.sessions : [];
  } catch (err) {
    console.warn('ไม่สามารถอ่านข้อมูล localStorage ได้:', err);
    return [];
  }
}

function formatDateTh(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString('th-TH', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit'
    });
  } catch {
    return iso || '';
  }
}

// ── เปิด / ปิด Picker Modal ───────────────────────────────────────
function openPicker() {
  pickerChoiceIndex = null;
  confirmAddBtn.disabled = true;
  pickerCount.textContent = 'ยังไม่ได้เลือกข้อมูล';
  renderPickerList();
  pickerOverlay.classList.add('show');
}

function closePicker() {
  pickerOverlay.classList.remove('show');
}

openPickerBtn.addEventListener('click', openPicker);
closePickerBtn.addEventListener('click', closePicker);
pickerOverlay.addEventListener('click', (e) => {
  if (e.target === pickerOverlay) closePicker();
});

function renderPickerList() {
  const sessions = loadUserSessions();

  if (sessions.length === 0) {
    pickerBody.innerHTML = `
      <div class="empty-state">
        <i class="fa-regular fa-folder-open"></i>
        <p>ยังไม่มีผลวิเคราะห์ที่บันทึกไว้ กรุณาไปที่หน้า "วิเคราะห์การปลูก" ก่อน</p>
      </div>`;
    return;
  }

  pickerBody.innerHTML = sessions.map((s, i) => {
    const cropName = s.result?.selected_crop?.name || s.inputs?.interested_crop || '-';
    const pct = Number(s.result?.selected_crop?.success_percent) || 0;
    const province = s.inputs?.province || '';
    const district = s.inputs?.district || '';
    return `
      <div class="picker-item" data-index="${i}">
        <div class="picker-item-check"><i class="fa-solid fa-check"></i></div>
        <div class="picker-item-main">
          <div class="picker-item-title">🌱 ${cropName}</div>
          <div class="picker-item-sub">${district ? district + ', ' : ''}${province} &nbsp;•&nbsp; โอกาสสำเร็จ ${pct}%</div>
          <div class="picker-item-time">${formatDateTh(s.time)}</div>
        </div>
      </div>`;
  }).join('');

  pickerBody.querySelectorAll('.picker-item').forEach(el => {
    el.addEventListener('click', () => {
      pickerBody.querySelectorAll('.picker-item').forEach(x => x.classList.remove('selected'));
      el.classList.add('selected');
      pickerChoiceIndex = Number(el.dataset.index);
      confirmAddBtn.disabled = false;
      pickerCount.textContent = 'เลือกแล้ว 1 รายการ';
    });
  });
}

confirmAddBtn.addEventListener('click', () => {
  if (pickerChoiceIndex === null) return;
  const sessions = loadUserSessions();
  selectedSession = sessions[pickerChoiceIndex];
  renderSelectedCard();
  closePicker();
  showToast('เลือกข้อมูลสำเร็จ');
  // ซ่อนผลแผนเก่า (ถ้ามี) เพราะเปลี่ยนข้อมูลต้นทางแล้ว
  planResultSection.style.display = 'none';
  planErrorSection.style.display = 'none';
});

clearSelectedBtn.addEventListener('click', () => {
  selectedSession = null;
  selectedSection.style.display = 'none';
  emptyStateSection.style.display = 'block';
  planResultSection.style.display = 'none';
  planErrorSection.style.display = 'none';
  renderMiniList();
});

// ── แสดงข้อมูลที่เลือกไว้บนหน้าเพจ ───────────────────────────────
const budgetLabel = {
  '5000-10000': '5,000–10,000 บาท',
  '10000-20000': '10,000–20,000 บาท',
  '20000+': '20,000 บาทขึ้นไป'
};
const areaLabel = { '5': '5 ไร่', '10': '10 ไร่', '20+': '20 ไร่ขึ้นไป' };

function chanceClass(c) {
  if (c === 'สูง') return 'chance-high';
  if (c === 'ต่ำ') return 'chance-low';
  return 'chance-mid';
}

function renderSelectedCard() {
  if (!selectedSession) return;
  const inputs = selectedSession.inputs || {};
  const sc = selectedSession.result?.selected_crop || {};
  const pct = Number(sc.success_percent) || 0;
  const cc = chanceClass(sc.success_chance);

  selectedCropCard.innerHTML = `
    <div class="crop-hero-header">
      <div class="crop-name-big">${sc.name || inputs.interested_crop || '-'}
        <small>ข้อมูลจากผลวิเคราะห์</small>
      </div>
      <div class="chance-badge ${cc}">
        <i class="fa-solid fa-chart-simple"></i>
        โอกาสสำเร็จ: ${sc.success_chance || 'ปานกลาง'} (${pct}%)
      </div>
    </div>
    <div class="info-bar" style="margin-top:.75rem;">
      ${inputs.province ? `<span class="info-chip">📍 ${inputs.province}</span>` : ''}
      ${inputs.district ? `<span class="info-chip">🗺️ ${inputs.district}</span>` : ''}
      ${inputs.budget ? `<span class="info-chip">💰 ${budgetLabel[inputs.budget] || inputs.budget}</span>` : ''}
      ${inputs.area ? `<span class="info-chip">📐 ${areaLabel[inputs.area] || inputs.area}</span>` : ''}
      ${inputs.water_source ? `<span class="info-chip">💧 ${inputs.water_source}</span>` : ''}
      ${inputs.planting_month ? `<span class="info-chip">📅 ${inputs.planting_month}</span>` : ''}
    </div>
    <div class="stats-row" style="margin-top:1rem;">
      <div class="stat-card">
        <div class="val">${sc.estimated_income || '-'}</div>
        <div class="lbl">บาท / ไร่ / ปี (ประมาณการ)</div>
      </div>
      <div class="stat-card">
        <div class="val">${sc.roi_months || '-'}</div>
        <div class="lbl">เดือน คืนทุน</div>
      </div>
      <div class="stat-card">
        <div class="val">${pct}%</div>
        <div class="lbl">โอกาสสำเร็จ</div>
      </div>
    </div>
  `;

  emptyStateSection.style.display = 'none';
  selectedSection.style.display = 'block';
  renderMiniList();
}

function renderMiniList() {
  if (!selectedSession) {
    selectedMiniList.innerHTML = `
      <div class="history-empty">
        <i class="fa-regular fa-folder-open"></i>
        ยังไม่ได้เลือกข้อมูล
      </div>`;
    return;
  }
  const sc = selectedSession.result?.selected_crop || {};
  const inputs = selectedSession.inputs || {};
  selectedMiniList.innerHTML = `
    <div class="mini-item">
      <i class="fa-solid fa-seedling"></i>
      <span>${sc.name || inputs.interested_crop || '-'}</span>
    </div>`;
}

// ── กดปุ่ม "วางแผน" → เรียก backend Gemini ───────────────────────
planBtn.addEventListener('click', async () => {
  if (!selectedSession) return;

  planResultSection.style.display = 'none';
  planErrorSection.style.display = 'none';
  planLoadingSection.style.display = 'block';

  const inputs = selectedSession.inputs || {};
  const sc = selectedSession.result?.selected_crop || {};

  try {
    const res = await fetch(`${API_BASE}/api/plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        crop_name: sc.name || inputs.interested_crop || '',
        province: inputs.province || '',
        district: inputs.district || '',
        budget: inputs.budget || '',
        area: inputs.area || '',
        water_source: inputs.water_source || '',
        planting_month: inputs.planting_month || '',
        success_chance: sc.success_chance || '',
        success_percent: sc.success_percent || '',
        estimated_income: sc.estimated_income || '',
        roi_months: sc.roi_months || '',
        pros: sc.pros || [],
        cons: sc.cons || [],
        tips: sc.tips || []
      })
    });

    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.error || `HTTP ${res.status}`);
    }

    const json = await res.json();
    if (json.success && json.data) {
      renderPlan(json.data);
    } else {
      throw new Error(json.error || 'โครงสร้างข้อมูลที่ได้รับไม่ถูกต้อง');
    }
  } catch (err) {
    console.error('Plan error:', err);
    planLoadingSection.style.display = 'none';
    planErrorSection.style.display = 'block';
    planErrorMsg.textContent = 'ไม่สามารถวางแผนการปลูกได้: ' + err.message;
  }
});

// ── Render ผลแผนการปลูกจาก AI ─────────────────────────────────────
function renderPlan(plan) {
  planLoadingSection.style.display = 'none';
  planErrorSection.style.display = 'none';
  planResultSection.style.display = 'block';

  document.getElementById('planOverview').textContent = plan.plan_overview || 'ไม่มีข้อมูลภาพรวม';

  const timeline = plan.timeline || [];
  document.getElementById('timelineList').innerHTML = timeline.length
    ? timeline.map((t, i) => `
      <div class="timeline-item">
        <div class="timeline-dot">${i + 1}</div>
        <div class="timeline-content">
          <div class="timeline-phase">${t.phase || '-'} <span class="timeline-duration">${t.duration || ''}</span></div>
          <div class="timeline-desc">${t.description || ''}</div>
        </div>
      </div>`).join('')
    : '<p style="color:#aaa;">ไม่มีข้อมูลขั้นตอน</p>';

  const y = plan.expected_yield || {};
  document.getElementById('yieldBox').innerHTML = `
    <div class="yield-amount">${y.amount || '-'} <span class="yield-unit">${y.unit || ''}</span></div>
    <p class="yield-note">${y.note || ''}</p>
  `;

  const w = plan.watering_schedule || {};
  document.getElementById('waterBox').innerHTML = `
    <div class="water-freq">
      <span class="water-num">${w.times_total || '-'}</span>
      <span class="water-label">ครั้ง (ตลอดฤดูปลูก)</span>
    </div>
    <div class="water-sub">≈ ${w.frequency_per_week || '-'} ครั้ง/สัปดาห์</div>
    <p class="water-note">${w.note || ''}</p>
  `;

  const equipment = plan.equipment || [];
  document.getElementById('equipmentList').innerHTML = equipment.length
    ? equipment.map(e => `<li><i class="fa-solid fa-circle-check"></i> ${e}</li>`).join('')
    : '<li>ไม่มีข้อมูลอุปกรณ์</li>';

  const fert = plan.fertilizer_plan || [];
  document.getElementById('fertilizerTableBody').innerHTML = fert.length
    ? fert.map(f => `
      <tr>
        <td>${f.stage || '-'}</td>
        <td>${f.type || '-'}</td>
        <td>${f.amount || '-'}</td>
        <td>${f.note || ''}</td>
      </tr>`).join('')
    : '<tr><td colspan="4" style="text-align:center;color:#aaa;">ไม่มีข้อมูลปุ๋ย</td></tr>';

  document.getElementById('finalAdvice').textContent = plan.final_advice || 'ไม่มีคำแนะนำเพิ่มเติม';

  planResultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Init: หา user ปัจจุบันจาก Firebase Auth (ถ้ามี) ─────────────
document.addEventListener('DOMContentLoaded', () => {
  renderMiniList();
  try {
    firebase.auth().onAuthStateChanged(user => {
      currentUserEmail = user?.email || 'anonymous';
    });
  } catch (err) {
    console.warn('Firebase auth ไม่พร้อมใช้งาน ใช้ผู้ใช้แบบ anonymous แทน:', err);
  }
});
