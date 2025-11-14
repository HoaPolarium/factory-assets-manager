from flask import Flask, request, jsonify, render_template_string, send_file
import os, json, io
from datetime import datetime, date
from openpyxl import Workbook

app = Flask(__name__)
DATA_FILE = "assets.json"

# ---------- Data helpers ----------
def _ensure_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({'assets': []}, f, ensure_ascii=False, indent=2)

def load_data():
    _ensure_data()
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def next_index(assets):
    return 1 if not assets else max(a.get('index', 0) for a in assets) + 1

def parse_date(d):
    # expecting 'YYYY-MM-DD' or empty
    if not d:
        return None
    try:
        return datetime.strptime(d, '%Y-%m-%d').date()
    except:
        return None

def find_asset_by_identifier(data, identifier):
    if not identifier:
        return None
    id_norm = identifier.strip().lower()
    for a in data['assets']:
        # match code, clc, serial (case-insensitive)
        if str(a.get('code','')).strip().lower() == id_norm:
            return a
        if str(a.get('clc','')).strip().lower() == id_norm:
            return a
        if str(a.get('serial','')).strip().lower() == id_norm:
            return a
    return None

# ---------- API ----------

@app.route('/api/assets', methods=['GET'])
def api_list_assets():
    return jsonify(load_data()['assets'])

@app.route('/api/assets', methods=['POST'])
def api_add_asset():
    payload = request.get_json() or {}
    # require clc and model now, remove coc
    required = ['clc','code','name','brand','model','serial','location','status','import_date','warranty_end','description']
    # normalized check (disallow empty strings for required fields)
    missing = [k for k in required if not payload.get(k)]
    if missing:
        return jsonify({'error':'Thiếu thông tin','missing_fields': missing}), 400
    data = load_data()
    if any(a['code'] == payload['code'] for a in data['assets']):
        return jsonify({'error':'Mã tài sản đã tồn tại'}), 400
    new = {
        'index': next_index(data['assets']),
        'clc': payload['clc'],
        'code': payload['code'],
        'name': payload['name'],
        'brand': payload['brand'],
        'model': payload['model'],
        'serial': payload['serial'],
        'location': payload['location'],
        'status': payload['status'],
        'import_date': payload['import_date'],
        'warranty_end': payload['warranty_end'],
        'description': payload['description'],
        # history will contain entries of two types:
        # { type:'fault', seq:1, fault:'...', fault_date:'YYYY-MM-DD', sent_date:'YYYY-MM-DD', return_date:'YYYY-MM-DD' }
        # { type:'calib', seq:1, calib_date:'YYYY-MM-DD', expire_date:'YYYY-MM-DD' }
        'history': []
    }
    data['assets'].append(new)
    save_data(data)
    return jsonify(new), 201

@app.route('/api/assets/<code>', methods=['GET'])
def api_get_asset(code):
    data = load_data()
    asset = next((a for a in data['assets'] if a['code'] == code), None)
    if not asset:
        return jsonify({'error':'Không tìm thấy mã tài sản'}), 404
    return jsonify(asset)

@app.route('/api/assets/<code>', methods=['PUT'])
def api_update_asset(code):
    payload = request.get_json() or {}
    required = ['clc','name','brand','model','description','serial','location','status','import_date','warranty_end']
    missing = [k for k in required if not payload.get(k)]
    if missing:
        return jsonify({'error':'Thiếu thông tin','missing_fields': missing}), 400
    data = load_data()
    asset = next((a for a in data['assets'] if a['code'] == code), None)
    if not asset:
        return jsonify({'error':'Không tìm thấy mã tài sản'}), 404
    for k in required:
        asset[k] = payload[k]
    save_data(data)
    return jsonify(asset)

@app.route('/api/assets', methods=['DELETE'])
def api_delete_asset_by_identifier():
    """
    DELETE /api/assets?identifier=...
    identifier can be code, clc or serial (case-insensitive)
    """
    identifier = request.args.get('identifier', '').strip()
    # also accept JSON body with identifier for clients that prefer it
    if not identifier and request.is_json:
        body = request.get_json()
        identifier = (body.get('identifier') or '').strip() if isinstance(body, dict) else ''
    if not identifier:
        return jsonify({'error':'Thiếu identifier để xóa (code/clc/serial)'}), 400
    data = load_data()
    # find by identifier
    asset = find_asset_by_identifier(data, identifier)
    if not asset:
        return jsonify({'error':'Không tìm thấy tài sản phù hợp'}), 404
    # remove
    new_assets = [a for a in data['assets'] if a is not asset]
    for i,a in enumerate(new_assets, start=1):
        a['index'] = i
    data['assets'] = new_assets
    save_data(data)
    return jsonify({'ok': True})

@app.route('/api/assets/<code>/history', methods=['GET'])
def api_get_history(code):
    data = load_data()
    asset = next((a for a in data['assets'] if a['code'] == code), None)
    if not asset:
        return jsonify({'error':'Không tìm thấy mã tài sản'}), 404
    return jsonify(asset.get('history', []))

@app.route('/api/assets/history', methods=['GET'])
def api_get_history_by_identifier():
    """
    GET /api/assets/history?identifier=...
    """
    identifier = request.args.get('identifier', '').strip()
    if not identifier:
        return jsonify({'error':'Thiếu identifier'}), 400
    data = load_data()
    asset = find_asset_by_identifier(data, identifier)
    if not asset:
        return jsonify({'error':'Không tìm thấy mã tài sản'}), 404
    return jsonify(asset.get('history', []))

@app.route('/api/assets/<code>/history', methods=['POST'])
def api_add_history(code):
    """
    Backwards-compatible route that uses <code> as asset code.
    Behaves same as /api/assets/history (POST) below.
    """
    # forward to new handler by building request-like call
    payload = request.get_json() or {}
    payload['identifier'] = code
    # reuse internal helper
    return _handle_add_history(payload)

@app.route('/api/assets/history', methods=['POST'])
def api_add_history_by_identifier():
    """
    POST /api/assets/history
    Body JSON:
    {
      "identifier": "value (code or clc or serial)",
      "type": "fault" or "calib",
      ... fields per type ...
    }
    """
    payload = request.get_json() or {}
    return _handle_add_history(payload)

def _handle_add_history(payload):
    # payload must include identifier and type
    identifier = (payload.get('identifier') or '').strip()
    payload_type = payload.get('type')
    if not identifier:
        return jsonify({'error':'Thiếu identifier (code/clc/serial)'}), 400
    if payload_type not in ('fault','calib'):
        return jsonify({'error':'Thiếu hoặc sai type (phải là "fault" hoặc "calib")'}), 400

    data = load_data()
    asset = find_asset_by_identifier(data, identifier)
    if not asset:
        return jsonify({'error':'Không tìm thấy mã tài sản'}), 404

    history = asset.setdefault('history', [])
    if payload_type == 'fault':
        required = ['fault','fault_date','sent_date']
        missing = [k for k in required if not payload.get(k)]
        if missing:
            return jsonify({'error':'Thiếu thông tin cho fault','missing_fields': missing}), 400
        # seq per fault type
        seq = sum(1 for h in history if h.get('type') == 'fault') + 1
        entry = {
            'type': 'fault',
            'seq': seq,
            'fault': payload['fault'],
            'fault_date': payload['fault_date'],
            'sent_date': payload['sent_date'],
            'return_date': payload.get('return_date') or ''
        }
        history.append(entry)
        save_data(data)
        return jsonify(entry), 201

    else:  # calib
        required = ['calib_date','expire_date']
        missing = [k for k in required if not payload.get(k)]
        if missing:
            return jsonify({'error':'Thiếu thông tin cho calib','missing_fields': missing}), 400
        seq = sum(1 for h in history if h.get('type') == 'calib') + 1
        entry = {
            'type': 'calib',
            'seq': seq,
            'calib_date': payload['calib_date'],
            'expire_date': payload['expire_date']
        }
        history.append(entry)

        # after adding, find latest calib (by calib_date) and update asset status if expired
        latest = None
        latest_cd = None
        for h in history:
            if h.get('type') == 'calib':
                cd = parse_date(h.get('calib_date'))
                if cd is None:
                    continue
                if latest is None or cd > latest_cd:
                    latest = h
                    latest_cd = cd
        if latest:
            exp = parse_date(latest.get('expire_date'))
            today = date.today()
            # If latest expire_date is before today, set status to 'Calib' (user requested auto-switch when expired)
            if exp and today > exp:
                asset['status'] = 'Calib'
            # else: do not change asset['status'] (keep whatever user had), adjust if you want different behavior
        save_data(data)
        return jsonify(entry), 201

@app.route('/export/excel', methods=['GET'])
def export_excel():
    data = load_data()
    wb = Workbook()
    ws = wb.active; ws.title = 'Assets'
    # updated header order per user request
    ws.append(['STT','Số CLC','Mã tài sản','Tên máy','Hãng','Model','Mô tả','Serial','Vị trí','Trạng thái','Ngày nhập','Hạn bảo hành'])
    for a in data['assets']:
        ws.append([a['index'], a.get('clc',''), a.get('code',''), a.get('name',''), a.get('brand',''), a.get('model',''), a.get('description',''), a.get('serial',''), a.get('location',''), a.get('status',''), a.get('import_date',''), a.get('warranty_end','')])
    ws2 = wb.create_sheet('History')
    ws2.append(['Mã tài sản','Loại','Lần','Tên lỗi/ngày calib','Ngày lỗi/Ngày calib','Ngày gửi đi','Ngày nhận về','Ngày hết hạn'])
    for a in data['assets']:
        for h in a.get('history', []):
            if h.get('type') == 'fault':
                ws2.append([a.get('code',''), 'fault', h.get('seq',''), h.get('fault',''), h.get('fault_date',''), h.get('sent_date',''), h.get('return_date',''), ''])
            elif h.get('type') == 'calib':
                ws2.append([a.get('code',''), 'calib', h.get('seq',''), '', h.get('calib_date',''), '', '', h.get('expire_date','')])
    stream = io.BytesIO(); wb.save(stream); stream.seek(0)
    fname = f"assets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(stream, as_attachment=True, download_name=fname, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# ---------- Frontend (HTML) ----------
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
      <td>${a.index}</td>\
      <td>${a.clc || ''}</td>\
      <td class="code-link">${a.code}</td>\
      <td>${a.name}</td>\
      <td>${a.brand}</td>\
      <td>${a.model || ''}</td>\
      <td>${a.description || ''}</td>\
      <td>${a.serial}</td>\
      <td>${a.location}</td>\
      <td>${a.status}</td>\
      <td>${a.import_date}</td>\
      <td>${a.warranty_end}</td>`;
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
  document.getElementById('edit_code').value = a.code;
  document.getElementById('edit_clc').value = a.clc || '';
  document.getElementById('edit_name').value = a.name;
  document.getElementById('edit_brand').value = a.brand;
  document.getElementById('edit_model').value = a.model || '';
  document.getElementById('edit_serial').value = a.serial;
  document.getElementById('edit_location').value = a.location;
  document.getElementById('edit_status').value = a.status;
  document.getElementById('edit_import').value = a.import_date;
  document.getElementById('edit_warranty').value = a.warranty_end;
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
  // Use identifier (we prefer code internally) but send identifier to server
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
  // clear fields
  ['hist_lookup','hist_fault','hist_fault_date','hist_sent','hist_return','hist_calib_date','hist_expire_date'].forEach(id=>document.getElementById(id).value='');
  hist_target_identifier = null;
}

async function toggleHistory(row, identifier){
  let next = row.nextSibling; if(next && next.classList && next.classList.contains('history-row')){ next.remove(); return; }
  // Use safe GET /api/assets/history?identifier=...
  const res = await fetch('/api/assets/history?identifier=' + encodeURIComponent(identifier)); const data = await res.json();
  const tr = document.createElement('tr'); tr.classList.add('history-row'); const td = document.createElement('td'); td.colSpan = 12;
  if(data.error || data.length === 0){ td.innerHTML = '<em>Chưa có lịch sử</em>'; }
  else{
    // separate into faults and calib
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

if __name__ == '__main__':
    print('Run server at http://127.0.0.1:5000')
    app.run(debug=True)
