# flask_app_supabase_fixed.py
"""
Flask app: Assets management using Supabase (compatible with Supabase Python Client v2)
Frontend HTML is embedded (the one you provided).
"""
import os
import tempfile
from datetime import datetime, date
from flask import Flask, request, jsonify, render_template_string, send_file
from supabase import create_client
import openpyxl

app = Flask(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Please set SUPABASE_URL and SUPABASE_KEY environment variables")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------
# Helpers
# -----------------------
def next_index():
    """Return next index (index_num)"""
    try:
        res = supabase.table("assets").select("index_num").order("index_num", desc=True).limit(1).execute()
        if getattr(res, "data", None) and len(res.data) > 0 and res.data[0].get("index_num"):
            return res.data[0]["index_num"] + 1
        return 1
    except Exception as e:
        app.logger.error("next_index error: %s", e)
        return 1

def find_asset_by_identifier(identifier):
    """Find asset by code or clc or serial (exact match). Return asset dict or None."""
    if not identifier:
        return None
    identifier = identifier.strip()
    # try code
    try:
        res = supabase.table("assets").select("*").or_(f"code.eq.{identifier},clc.eq.{identifier},serial.eq.{identifier}").limit(1).execute()
    except Exception as e:
        app.logger.error("find_asset error: %s", e)
        return None
    return res.data[0] if getattr(res, "data", None) else None

def transform_asset_for_frontend(a):
    """Map DB asset to frontend shape (frontend expects 'index' property)."""
    if not a:
        return a
    out = dict(a)  # shallow copy
    # map index_num -> index for frontend
    if "index_num" in out:
        out["index"] = out.get("index_num")
    else:
        # keep existing index if any
        if "index" not in out:
            out["index"] = None
    return out

# -----------------------
# Routes (API)
# -----------------------

# Serve the provided HTML UI at '/'
INDEX_HTML = r'''  <!-- (Your full HTML omitted here for brevity in this snippet) -->
'''  # We will later overwrite with the full template content (below)

# We'll set INDEX_HTML to the long HTML from user's message:
INDEX_HTML = r'''
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Quản lý tài sản</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body{background:#f6f9fc;padding:20px;font-family:Arial}
    .card{box-shadow:0 2px 8px rgba(0,0,0,0.06)}
    th,td{vertical-align:middle}
    .filter-row input{width:100%;padding:4px}
    .code-link{color:#0d6efd;cursor:pointer}
    .history-row td{background:#fbfbfb}
  </style>
</head>
<body>
<div class="container">
  <div class="d-flex justify-content-between align-items-center mb-3">
    <h3 class="mb-0">Quản lý tài sản</h3>
    <div>
      <button class="btn btn-success me-1" onclick="openAdd()">Thêm sản phẩm</button>
      <button class="btn btn-secondary me-1" onclick="openEdit()">Sửa thông tin</button>
      <button class="btn btn-danger me-1" onclick="openDelete()">Xóa</button>
      <button class="btn btn-outline-primary" onclick="openHist()">Thêm lịch sử</button>
      <a class="btn btn-outline-success ms-2" href="/export/excel">Xuất Excel</a>
    </div>
  </div>

  <div class="card p-3">
    <div class="table-responsive">
      <table id="assetTable" class="table table-striped table-bordered align-middle">
        <thead>
          <tr>
            <th>STT</th><th>Số CLC</th><th>Mã tài sản</th><th>Tên máy</th><th>Hãng</th><th>Model</th><th>Mô tả</th><th>Serial</th><th>Vị trí</th><th>Trạng thái</th><th>Ngày nhập</th><th>Hạn bảo hành</th>
          </tr>
          <tr class="filter-row">
            <th><input data-col="0" oninput="applyFilters()"></th>
            <th><input data-col="1" oninput="applyFilters()"></th>
            <th><input data-col="2" oninput="applyFilters()"></th>
            <th><input data-col="3" oninput="applyFilters()"></th>
            <th><input data-col="4" oninput="applyFilters()"></th>
            <th><input data-col="5" oninput="applyFilters()"></th>
            <th><input data-col="6" oninput="applyFilters()"></th>
            <th><input data-col="7" oninput="applyFilters()"></th>
            <th><input data-col="8" oninput="applyFilters()"></th>
            <th><input data-col="9" oninput="applyFilters()"></th>
            <th><input data-col="10" oninput="applyFilters()"></th>
            <th><input data-col="11" oninput="applyFilters()"></th>
          </tr>
        </thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- Modals -->
<!-- Add -->
<div class="modal" id="modalAdd" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
  <div class="modal-header"><h5 class="modal-title">Thêm sản phẩm</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
  <div class="modal-body">
    <div id="addAlert" class="alert alert-danger d-none"></div>
    <div class="mb-2"><label class="form-label">Số CLC</label><input id="add_clc" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Mã tài sản</label><input id="add_code" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Tên máy</label><input id="add_name" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Hãng</label><input id="add_brand" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Model</label><input id="add_model" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Mô tả</label><input id="add_description" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Serial</label><input id="add_serial" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Vị trí</label><input id="add_location" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Trạng thái</label>
      <select id="add_status" class="form-select">
        <option>OK</option><option>NG</option><option>Maintenance/Warranty</option><option>Calib</option>
      </select>
    </div>
    <div class="mb-2"><label class="form-label">Ngày nhập</label><input id="add_import" class="form-control" type="date"></div>
    <div class="mb-2"><label class="form-label">Hạn bảo hành</label><input id="add_warranty" class="form-control" type="date"></div>
  </div>
  <div class="modal-footer"><button class="btn btn-secondary" data-bs-dismiss="modal">Đóng</button><button class="btn btn-primary" onclick="doAdd()">Lưu</button></div>
</div></div></div>

<!-- Edit -->
<div class="modal" id="modalEdit" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
  <div class="modal-header"><h5 class="modal-title">Sửa thông tin tài sản</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
  <div class="modal-body">
    <div id="editAlert" class="alert alert-danger d-none"></div>
    <div class="mb-2 d-flex"><input id="edit_lookup_code" class="form-control me-2" placeholder="Nhập mã tài sản để load"><button class="btn btn-outline-primary" onclick="loadForEdit()">Tải</button></div>
    <div id="editForm" style="display:none">
      <div class="mb-2"><label class="form-label">Mã tài sản (không sửa)</label><input id="edit_code" class="form-control" disabled></div>
      <div class="mb-2"><label class="form-label">Số CLC</label><input id="edit_clc" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Tên máy</label><input id="edit_name" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Hãng</label><input id="edit_brand" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Model</label><input id="edit_model" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Mô tả</label><input id="edit_description" class="form-control" type="text"></div>
      <div class="mb-2"><label class="form-label">Serial</label><input id="edit_serial" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Vị trí</label><input id="edit_location" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Trạng thái</label><select id="edit_status" class="form-select"><option>OK</option><option>NG</option><option>Maintenance/Warranty</option><option>Calib</option></select></div>
      <div class="mb-2"><label class="form-label">Ngày nhập</label><input id="edit_import" class="form-control" type="date"></div>
      <div class="mb-2"><label class="form-label">Hạn bảo hành</label><input id="edit_warranty" class="form-control" type="date"></div>  
    </div>
  </div>
  <div class="modal-footer"><button class="btn btn-secondary" data-bs-dismiss="modal">Đóng</button><button class="btn btn-primary" onclick="doEdit()">Lưu</button></div>
</div></div></div>

<!-- Delete -->
<div class="modal" id="modalDelete" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
  <div class="modal-header"><h5 class="modal-title">Xóa tài sản</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
  <div class="modal-body"><input id="del_code" class="form-control" placeholder="Nhập Số CLC / Mã tài sản / Serial"></div>
  <div class="modal-footer"><button class="btn btn-secondary" data-bs-dismiss="modal">Đóng</button><button class="btn btn-danger" onclick="doDelete()">Xóa</button></div>
</div></div></div>

<!-- History -->
<div class="modal" id="modalHist" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
  <div class="modal-header"><h5 class="modal-title">Thêm lịch sử</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
  <div class="modal-body">
    <div id="histAlert" class="alert alert-danger d-none"></div>

    <!-- Lookup by CLC or Serial -->
    <div class="mb-2"><label class="form-label">Tìm tài sản (Số CLC hoặc Serial)</label>
      <div class="d-flex">
        <input id="hist_lookup" class="form-control me-2" placeholder="Nhập Số CLC hoặc Serial">
        <button class="btn btn-outline-primary" onclick="lookupAssetForHist()">Tìm</button>
      </div>
      <div id="hist_found" class="mt-2 small text-muted"></div>
    </div>

    <div class="mb-2">
      <label class="form-label">Loại lịch sử</label>
      <select id="hist_type" class="form-select" onchange="onHistTypeChange()">
        <option value="fault">Lỗi</option>
        <option value="calib">Calib</option>
      </select>
    </div>

    <!-- Fault form -->
    <div id="hist_fault_form" style="display:block">
      <div class="mb-2"><label class="form-label">Tên lỗi</label><input id="hist_fault" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Ngày lỗi</label><input id="hist_fault_date" class="form-control" type="date"></div>
      <div class="mb-2"><label class="form-label">Ngày gửi đi</label><input id="hist_sent" class="form-control" type="date"></div>
      <div class="mb-2"><label class="form-label">Ngày nhận về (tùy chọn)</label><input id="hist_return" class="form-control" type="date"></div>
    </div>

    <!-- Calib form -->
    <div id="hist_calib_form" style="display:none">
      <div class="mb-2"><label class="form-label">Ngày calib</label><input id="hist_calib_date" class="form-control" type="date"></div>
      <div class="mb-2"><label class="form-label">Ngày hết hạn</label><input id="hist_expire_date" class="form-control" type="date"></div>
    </div>

  </div>
  <div class="modal-footer"><button class="btn btn-secondary" data-bs-dismiss="modal">Đóng</button><button class="btn btn-primary" onclick="doAddHistory()">Lưu</button></div>
</div></div></div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
<script>
const addModal = new bootstrap.Modal(document.getElementById('modalAdd'));
const editModal = new bootstrap.Modal(document.getElementById('modalEdit'));
const delModal = new bootstrap.Modal(document.getElementById('modalDelete'));
const histModal = new bootstrap.Modal(document.getElementById('modalHist'));

let hist_target_identifier = null; // will store the identifier (could be clc, code, or serial)

function openAdd(){ document.getElementById('addAlert').classList.add('d-none'); addModal.show(); }
function openEdit(){ document.getElementById('editAlert').classList.add('d-none'); editModal.show(); }
function openDelete(){ delModal.show(); }
function openHist(){ document.getElementById('histAlert').classList.add('d-none'); document.getElementById('hist_found').innerText=''; hist_target_identifier = null; histModal.show(); }

async function loadTable(){
  const res = await fetch('/api/assets'); 
  const list = await res.json();
  const tbody = document.getElementById('tbody'); 
  tbody.innerHTML = '';
  for(const a of list){
    const tr = document.createElement('tr');
    tr.innerHTML = `\
      <td>${a.index || ''}</td>\
      <td>${a.clc || ''}</td>\
      <td class="code-link">${a.code || ''}</td>\
      <td>${a.name || ''}</td>\
      <td>${a.brand || ''}</td>\
      <td>${a.model || ''}</td>\
      <td>${a.description || ''}</td>\
      <td>${a.serial || ''}</td>\
      <td>${a.location || ''}</td>\
      <td>${a.status || ''}</td>\
      <td>${a.import_date || ''}</td>\
      <td>${a.warranty_end || ''}</td>`;
    tr.querySelector('.code-link').onclick = () => toggleHistory(tr, a.code);
    tbody.appendChild(tr);
  }
  applyFilters();
}

function applyFilters(){
  const table = document.getElementById('assetTable');
  const filters = Array.from(table.tHead.rows[1].querySelectorAll('input')).map(i=>i.value.trim().toLowerCase());
  const rows = table.tBodies[0].rows;
  for(const r of rows){
    if(r.classList && r.classList.contains('history-row')) continue;
    let visible = true;
    for(let c=0;c<filters.length;c++){
      if(!filters[c]) continue;
      const cell = r.cells[c];
      if(!cell || cell.textContent.toLowerCase().indexOf(filters[c]) === -1){ visible = false; break; }
    }
    r.style.display = visible ? '' : 'none';
    const next = r.nextSibling;
    if(next && next.classList && next.classList.contains('history-row')) next.style.display = visible ? '' : 'none';
  }
}

async function doAdd(){
  const payload = {
    clc: document.getElementById('add_clc').value.trim(),
    code: document.getElementById('add_code').value.trim(),
    name: document.getElementById('add_name').value.trim(),
    brand: document.getElementById('add_brand').value.trim(),
    model: document.getElementById('add_model').value.trim(),
    serial: document.getElementById('add_serial').value.trim(),
    location: document.getElementById('add_location').value.trim(),
    status: document.getElementById('add_status').value,
    import_date: document.getElementById('add_import').value,
    warranty_end: document.getElementById('add_warranty').value,
    description: document.getElementById('add_description').value.trim()
  };
  const res = await fetch('/api/assets', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  const data = await res.json();
  if(!res.ok){
    const el = document.getElementById('addAlert'); el.classList.remove('d-none');
    if(data.missing_fields) el.innerText = data.error + ': ' + data.missing_fields.join(', '); else el.innerText = data.error || 'Có lỗi';
    return;
  }
  addModal.hide(); loadTable();
  ['add_clc','add_code','add_name','add_brand','add_model','add_serial','add_location','add_import','add_warranty','add_description'].forEach(id=>document.getElementById(id).value='');
}

async function loadForEdit(){
  const code = document.getElementById('edit_lookup_code').value.trim();
  if(!code){ document.getElementById('editAlert').classList.remove('d-none'); document.getElementById('editAlert').innerText='Nhập mã tài sản'; return; }
  const res = await fetch('/api/assets/' + encodeURIComponent(code));
  if(!res.ok){ const d = await res.json(); document.getElementById('editAlert').classList.remove('d-none'); document.getElementById('editAlert').innerText = d.error || 'Không tìm thấy'; return; }
  const a = await res.json();
  document.getElementById('edit_code').value = a.code || '';
  document.getElementById('edit_clc').value = a.clc || '';
  document.getElementById('edit_name').value = a.name || '';
  document.getElementById('edit_brand').value = a.brand || '';
  document.getElementById('edit_model').value = a.model || '';
  document.getElementById('edit_serial').value = a.serial || '';
  document.getElementById('edit_location').value = a.location || '';
  document.getElementById('edit_status').value = a.status || '';
  document.getElementById('edit_import').value = a.import_date || '';
  document.getElementById('edit_warranty').value = a.warranty_end || '';
  document.getElementById('edit_description').value = a.description || '';
  document.getElementById('editForm').style.display = 'block';
}

async function doEdit(){
  const code = document.getElementById('edit_code').value;
  const payload = {
    clc: document.getElementById('edit_clc').value.trim(),
    name: document.getElementById('edit_name').value.trim(),
    brand: document.getElementById('edit_brand').value.trim(),
    model: document.getElementById('edit_model').value.trim(),
    serial: document.getElementById('edit_serial').value.trim(),
    location: document.getElementById('edit_location').value.trim(),
    status: document.getElementById('edit_status').value,
    import_date: document.getElementById('edit_import').value,
    warranty_end: document.getElementById('edit_warranty').value,
    description: document.getElementById('edit_description').value.trim()
  };
  const res = await fetch('/api/assets/' + encodeURIComponent(code), {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  const data = await res.json();
  if(!res.ok){ if(data.missing_fields) { document.getElementById('editAlert').classList.remove('d-none'); document.getElementById('editAlert').innerText = data.error + ': ' + data.missing_fields.join(', '); } else { document.getElementById('editAlert').classList.remove('d-none'); document.getElementById('editAlert').innerText = data.error || 'Có lỗi'; } return; }
  editModal.hide(); loadTable(); document.getElementById('editForm').style.display='none'; document.getElementById('edit_lookup_code').value='';
}

async function doDelete(){
  const identifier = document.getElementById('del_code').value.trim();
  if(!identifier) return alert('Nhập Số CLC / Mã / Serial để xóa');
  if(!confirm('Bạn có chắc muốn xóa: ' + identifier + ' ?')) return;
  const res = await fetch('/api/assets?identifier=' + encodeURIComponent(identifier), {method:'DELETE'});
  const data = await res.json();
  if(!res.ok) return alert(data.error || 'Có lỗi');
  delModal.hide(); loadTable(); document.getElementById('del_code').value='';
}

// lookup asset by CLC or Serial for history modal
async function lookupAssetForHist(){
  const v = document.getElementById('hist_lookup').value.trim();
  const el = document.getElementById('hist_found'); el.innerText = '';
  if(!v){ el.innerText = 'Nhập Số CLC hoặc Serial để tìm'; return; }
  const res = await fetch('/api/assets'); const list = await res.json();
  const found = list.find(a => (a.clc && a.clc.toLowerCase() === v.toLowerCase()) || (a.serial && a.serial.toLowerCase() === v.toLowerCase()));
  if(!found){ el.innerText = 'Không tìm thấy tài sản'; hist_target_identifier = null; return; }
  hist_target_identifier = found.code || found.clc || found.serial;
  el.innerText = `Tìm thấy: ${found.code} — ${found.name} (Số CLC: ${found.clc || ''})`;
}

function onHistTypeChange(){
  const t = document.getElementById('hist_type').value;
  document.getElementById('hist_fault_form').style.display = t === 'fault' ? 'block' : 'none';
  document.getElementById('hist_calib_form').style.display = t === 'calib' ? 'block' : 'none';
}

async function doAddHistory(){
  if(!hist_target_identifier){
    const el = document.getElementById('histAlert'); el.classList.remove('d-none'); el.innerText = 'Bạn phải tìm và chọn tài sản bằng Số CLC hoặc Serial trước.'; return;
  }
  const type = document.getElementById('hist_type').value;
  let payload = { identifier: hist_target_identifier, type };
  if(type === 'fault'){
    payload.fault = document.getElementById('hist_fault').value.trim();
    payload.fault_date = document.getElementById('hist_fault_date').value;
    payload.sent_date = document.getElementById('hist_sent').value;
    payload.return_date = document.getElementById('hist_return').value || '';
  } else {
    payload.calib_date = document.getElementById('hist_calib_date').value;
    payload.expire_date = document.getElementById('hist_expire_date').value;
  }
  const res = await fetch('/api/assets/history', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  const data = await res.json();
  if(!res.ok){ const el = document.getElementById('histAlert'); el.classList.remove('d-none'); if(data.missing_fields) el.innerText = data.error + ': ' + data.missing_fields.join(', '); else el.innerText = data.error || 'Có lỗi'; return; }
  histModal.hide(); loadTable();
  ['hist_lookup','hist_fault','hist_fault_date','hist_sent','hist_return','hist_calib_date','hist_expire_date'].forEach(id=>document.getElementById(id).value='');
  hist_target_identifier = null;
}

async function toggleHistory(row, identifier){
  let next = row.nextSibling; if(next && next.classList && next.classList.contains('history-row')){ next.remove(); return; }
  const res = await fetch('/api/assets/history?identifier=' + encodeURIComponent(identifier)); const data = await res.json();
  const tr = document.createElement('tr'); tr.classList.add('history-row'); const td = document.createElement('td'); td.colSpan = 12;
  if(data.error || data.length === 0){ td.innerHTML = '<em>Chưa có lịch sử</em>'; }
  else{
    const faults = data.filter(h => h.type === 'fault');
    const calibs = data.filter(h => h.type === 'calib');
    let html = '';
    if(faults.length){
      html += '<h6>Lịch sử lỗi</h6><table class="table table-sm"><thead><tr><th>STT</th><th>Tên lỗi</th><th>Ngày lỗi</th><th>Ngày gửi</th><th>Ngày nhận</th></tr></thead><tbody>';
      for(const h of faults) html += `<tr><td>${h.seq}</td><td>${h.fault}</td><td>${h.fault_date}</td><td>${h.sent_date}</td><td>${h.return_date || ''}</td></tr>`;
      html += '</tbody></table>';
    } else {
      html += '<h6>Lịch sử lỗi</h6><div><em>Không có</em></div>';
    }
    if(calibs.length){
      html += '<h6 class="mt-2">Lịch sử Calib</h6><table class="table table-sm"><thead><tr><th>STT</th><th>Ngày calib</th><th>Ngày hết hạn</th></tr></thead><tbody>';
      for(const h of calibs) html += `<tr><td>${h.seq}</td><td>${h.calib_date}</td><td>${h.expire_date}</td></tr>`;
      html += '</tbody></table>';
    } else {
      html += '<h6 class="mt-2">Lịch sử Calib</h6><div><em>Không có</em></div>';
    }
    td.innerHTML = html;
  }
  tr.appendChild(td); row.parentNode.insertBefore(tr, row.nextSibling);
}

document.addEventListener('DOMContentLoaded', ()=>{ loadTable(); });
</script>
</body>
</html>
'''

@app.route('/')
def index_page():
    return render_template_string(INDEX_HTML)

# ---- API: list assets ----
@app.route("/api/assets", methods=["GET"])
def api_list_assets():
    try:
        res = supabase.table("assets").select("*").order("index_num", desc=False).execute()
        assets = res.data or []
        # transform for frontend (index)
        out = [transform_asset_for_frontend(a) for a in assets]
        return jsonify(out), 200
    except Exception as e:
        app.logger.error("api_list_assets error: %s", e)
        return jsonify({"error": str(e)}), 500

# ---- API: add asset ----
@app.route("/api/assets", methods=["POST"])
def api_add_asset():
    data = request.get_json() or {}
    # minimal validation similar to your frontend (frontend will show missing_fields if backend returns such)
    required = ['clc','code','name','brand','model','serial','location','status','import_date','warranty_end','description']
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"error": "Thiếu thông tin", "missing_fields": missing}), 400
    try:
        # duplicate by code
        dup = supabase.table("assets").select("code").eq("code", data["code"]).limit(1).execute()
        if getattr(dup, "data", None):
            return jsonify({"error": "Mã tài sản đã tồn tại"}), 400
        data["index_num"] = next_index()
        ins = supabase.table("assets").insert(data).execute()
        created = ins.data[0]
        return jsonify(transform_asset_for_frontend(created)), 201
    except Exception as e:
        app.logger.error("api_add_asset error: %s", e)
        return jsonify({"error": str(e)}), 500

# ---- API: get asset by code (returns asset object directly) ----
@app.route("/api/assets/<code>", methods=["GET"])
def api_get_asset(code):
    try:
        res = supabase.table("assets").select("*").eq("code", code).limit(1).execute()
        if not getattr(res, "data", None):
            return jsonify({"error": "Không tìm thấy mã tài sản"}), 404
        asset = transform_asset_for_frontend(res.data[0])
        return jsonify(asset), 200
    except Exception as e:
        app.logger.error("api_get_asset error: %s", e)
        return jsonify({"error": str(e)}), 500

# ---- API: update asset ----
@app.route("/api/assets/<code>", methods=["PUT"])
def api_update_asset(code):
    data = request.get_json() or {}
    required = ['clc','name','brand','model','description','serial','location','status','import_date','warranty_end']
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"error": "Thiếu thông tin", "missing_fields": missing}), 400
    try:
        res = supabase.table("assets").update(data).eq("code", code).execute()
        if not getattr(res, "data", None):
            return jsonify({"error": "Không tìm thấy mã tài sản"}), 404
        updated = transform_asset_for_frontend(res.data[0])
        return jsonify(updated), 200
    except Exception as e:
        app.logger.error("api_update_asset error: %s", e)
        return jsonify({"error": str(e)}), 500

# ---- API: delete asset by identifier (code/clc/serial) ----
@app.route("/api/assets", methods=["DELETE"])
def api_delete_asset():
    identifier = request.args.get("identifier") or (request.get_json(silent=True) or {}).get("identifier")
    if not identifier:
        return jsonify({"error": "Missing identifier"}), 400
    try:
        asset = find_asset_by_identifier(identifier)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404
        code = asset.get("code")
        # delete history and asset
        supabase.table("asset_history").delete().eq("asset_code", code).execute()
        supabase.table("assets").delete().eq("code", code).execute()
        # reindex
        remaining = supabase.table("assets").select("code").order("index_num", desc=False).execute()
        idx = 1
        for r in (remaining.data or []):
            try:
                supabase.table("assets").update({"index_num": idx}).eq("code", r["code"]).execute()
            except Exception as e:
                app.logger.error("reindex error for %s: %s", r.get("code"), e)
            idx += 1
        return jsonify({"ok": True}), 200
    except Exception as e:
        app.logger.error("api_delete_asset error: %s", e)
        return jsonify({"error": str(e)}), 500

# ---- API: get history by code ----
@app.route("/api/assets/<code>/history", methods=["GET"])
def api_get_history(code):
    try:
        res = supabase.table("asset_history").select("*").eq("asset_code", code).order("seq", desc=False).execute()
        return jsonify(res.data or []), 200
    except Exception as e:
        app.logger.error("api_get_history error: %s", e)
        return jsonify({"error": str(e)}), 500

# ---- API: get history by identifier ----
@app.route("/api/assets/history", methods=["GET"])
def api_get_history_identifier():
    identifier = request.args.get("identifier")
    if not identifier:
        return jsonify({"error": "Missing identifier"}), 400
    try:
        asset = find_asset_by_identifier(identifier)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404
        code = asset.get("code")
        res = supabase.table("asset_history").select("*").eq("asset_code", code).order("seq", desc=False).execute()
        return jsonify(res.data or []), 200
    except Exception as e:
        app.logger.error("api_get_history_identifier error: %s", e)
        return jsonify({"error": str(e)}), 500

def normalize_dates(data):
    for field in ["fault_date", "sent_date", "return_date", "calib_date", "expire_date"]:
        if field in data and data[field] == "":
            data[field] = None
    return data

# ---- API: add history by identifier (body contains identifier) ----
@app.route("/api/assets/history", methods=["POST"])
def api_add_history_identifier():
    body = request.get_json() or {}
    body = normalize_dates(body)
    identifier = body.get("identifier")
    if not identifier:
        return jsonify({"error": "Missing identifier"}), 400
    if body.get("type") not in ("fault", "calib"):
        return jsonify({"error": "Missing or invalid type (must be 'fault' or 'calib')"}), 400
    try:
        asset = find_asset_by_identifier(identifier)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404
        code = asset.get("code")
        last = supabase.table("asset_history").select("seq").eq("asset_code", code).order("seq", desc=True).limit(1).execute()
        seq = (last.data[0]["seq"] + 1) if getattr(last, "data", None) else 1
        entry = dict(body)
        entry["asset_code"] = code
        entry["seq"] = seq
        # validate required per type
        if entry["type"] == "fault":
            for k in ("fault", "fault_date", "sent_date"):
                if not entry.get(k):
                    return jsonify({"error": "Thiếu thông tin cho fault", "missing_fields": [k]}), 400
        else:  # calib
            for k in ("calib_date", "expire_date"):
                if not entry.get(k):
                    return jsonify({"error": "Thiếu thông tin cho calib", "missing_fields": [k]}), 400
        ins = supabase.table("asset_history").insert(entry).execute()
        # If calib, maybe update asset status if expired (kept from your original logic)
        if entry["type"] == "calib":
            try:
                all_calibs = supabase.table("asset_history").select("*").eq("asset_code", code).eq("type", "calib").execute()
                latest = None; latest_cd = None
                for h in (all_calibs.data or []):
                    cd = None
                    try:
                        cd = datetime.strptime(h.get("calib_date",""), "%Y-%m-%d").date()
                    except Exception:
                        cd = None
                    if cd and (latest_cd is None or cd > latest_cd):
                        latest_cd = cd; latest = h
                if latest:
                    exp = None
                    try:
                        exp = datetime.strptime(latest.get("expire_date",""), "%Y-%m-%d").date()
                    except Exception:
                        exp = None
                    today = date.today()
                    if exp and today > exp:
                        supabase.table("assets").update({"status": "Calib"}).eq("code", code).execute()
            except Exception as e:
                app.logger.error("post-calib check error: %s", e)
        return jsonify(ins.data[0]), 201
    except Exception as e:
        app.logger.error("api_add_history_identifier error: %s", e)
        return jsonify({"error": str(e)}), 500

# ---- API: add history by code (route variant) ----
@app.route("/api/assets/<code>/history", methods=["POST"])
def api_add_history_code(code):
    body = request.get_json() or {}
    # forward to identifier handler by adding identifier = code
    body["identifier"] = code
    return api_add_history_identifier()

# ---- EXPORT EXCEL ----
@app.route("/export/excel", methods=["GET"])
def export_excel():
    try:
        assets = supabase.table("assets").select("*").order("index_num", desc=False).execute()
        history = supabase.table("asset_history").select("*").order("seq", desc=False).execute()
        wb = openpyxl.Workbook()
        ws1 = wb.active; ws1.title = "Assets"
        if assets.data:
            headers = ["index","clc","code","name","brand","model","description","serial","location","status","import_date","warranty_end"]
            ws1.append(headers)
            for a in assets.data:
                row = [
                    a.get("index_num"),
                    a.get("clc",""),
                    a.get("code",""),
                    a.get("name",""),
                    a.get("brand",""),
                    a.get("model",""),
                    a.get("description",""),
                    a.get("serial",""),
                    a.get("location",""),
                    a.get("status",""),
                    a.get("import_date",""),
                    a.get("warranty_end","")
                ]
                ws1.append(row)
        ws2 = wb.create_sheet("History")
        ws2.append(['asset_code','type','seq','fault','fault_date','sent_date','return_date','calib_date','expire_date'])
        for h in (history.data or []):
            ws2.append([
                h.get("asset_code",""),
                h.get("type",""),
                h.get("seq",""),
                h.get("fault",""),
                h.get("fault_date",""),
                h.get("sent_date",""),
                h.get("return_date",""),
                h.get("calib_date",""),
                h.get("expire_date","")
            ])
        fp = tempfile.gettempdir() + "/assets_export.xlsx"
        wb.save(fp)
        return send_file(fp, as_attachment=True, download_name="assets.xlsx")
    except Exception as e:
        app.logger.error("export_excel error: %s", e)
        return jsonify({"error": str(e)}), 500

# -----------------------
# Run
# -----------------------
if __name__ == "__main__":
    from os import environ
    port = int(environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
