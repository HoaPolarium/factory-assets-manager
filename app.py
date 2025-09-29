from flask import Flask, request, jsonify, render_template_string, send_file
import os, json, io
from datetime import datetime
from openpyxl import Workbook

app = Flask(__name__)
DATA_FILE = '/var/data/assets.json'

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

# ---------- API ----------

@app.route('/api/assets', methods=['GET'])
def api_list_assets():
    return jsonify(load_data()['assets'])

@app.route('/api/assets', methods=['POST'])
def api_add_asset():
    payload = request.get_json() or {}
    required = ['code','name','brand','serial','location','status','import_date','warranty_end','description','coc']
    missing = [k for k in required if not payload.get(k) and payload.get(k) != '' and payload.get(k) is None]
    # note: allow empty description/coc? spec says add fields, we'll require them (per request)
    missing = [k for k in required if not payload.get(k)]
    if missing:
        return jsonify({'error':'Thiếu thông tin','missing_fields': missing}), 400
    data = load_data()
    if any(a['code'] == payload['code'] for a in data['assets']):
        return jsonify({'error':'Mã tài sản đã tồn tại'}), 400
    new = {
        'index': next_index(data['assets']),
        'code': payload['code'],
        'name': payload['name'],
        'brand': payload['brand'],
        'serial': payload['serial'],
        'location': payload['location'],
        'status': payload['status'],
        'import_date': payload['import_date'],
        'warranty_end': payload['warranty_end'],
        'description': payload['description'],
        'coc': payload['coc'],
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
    required = ['name','brand','description','serial','coc','location','status','import_date','warranty_end']
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

@app.route('/api/assets/<code>', methods=['DELETE'])
def api_delete_asset(code):
    data = load_data()
    assets = data['assets']
    new_assets = [a for a in assets if a['code'] != code]
    if len(new_assets) == len(assets):
        return jsonify({'error':'Không tìm thấy mã tài sản'}), 404
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

@app.route('/api/assets/<code>/history', methods=['POST'])
def api_add_history(code):
    payload = request.get_json() or {}
    required = ['fault','sent_date']
    missing = [k for k in required if not payload.get(k)]
    if missing:
        return jsonify({'error':'Thiếu thông tin','missing_fields': missing}), 400
    data = load_data()
    asset = next((a for a in data['assets'] if a['code'] == code), None)
    if not asset:
        return jsonify({'error':'Không tìm thấy mã tài sản'}), 404
    seq = len(asset.get('history', [])) + 1
    entry = {'seq': seq, 'fault': payload['fault'], 'sent_date': payload['sent_date']}
    asset.setdefault('history', []).append(entry)
    save_data(data)
    return jsonify(entry), 201

@app.route('/export/excel', methods=['GET'])
def export_excel():
    data = load_data()
    wb = Workbook()
    ws = wb.active; ws.title = 'Assets'
    ws.append(['STT','Mã tài sản','Tên máy','Hãng','Mô tả','Serial','CoC','Vị trí','Trạng thái','Ngày nhập','Hạn bảo hành'])
    for a in data['assets']:
        ws.append([a['index'], a['code'], a['name'], a['brand'], a['description'], a['serial'], a['coc'], a['location'], a['status'], a['import_date'], a['warranty_end']])
    ws2 = wb.create_sheet('History')
    ws2.append(['Mã tài sản','Lần','Lỗi','Ngày gửi đi'])
    for a in data['assets']:
        for h in a.get('history', []):
            ws2.append([a['code'], h['seq'], h['fault'], h['sent_date']])
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
            <th>STT</th><th>Mã tài sản</th><th>Tên máy</th><th>Hãng</th><th>Mô tả</th><th>Serial</th><th>CoC</th><th>Vị trí</th><th>Trạng thái</th><th>Ngày nhập</th><th>Hạn bảo hành</th>
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
    <div class="mb-2"><label class="form-label">Mã tài sản</label><input id="add_code" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Tên máy</label><input id="add_name" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Hãng</label><input id="add_brand" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Mô tả</label><input id="add_description" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Serial</label><input id="add_serial" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">CoC</label><input id="add_coc" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Vị trí</label><input id="add_location" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Trạng thái</label>
      <select id="add_status" class="form-select"><option>OK</option><option>NG</option><option>Maintenance/Warranty</option></select>
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
      <div class="mb-2"><label class="form-label">Tên máy</label><input id="edit_name" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Hãng</label><input id="edit_brand" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Mô tả</label><input id="edit_description" class="form-control" type="text"></div>
      <div class="mb-2"><label class="form-label">Serial</label><input id="edit_serial" class="form-control"></div>
      <div class="mb-2"><label class="form-label">CoC</label><input id="edit_coc" class="form-control" type="text"></div>
      <div class="mb-2"><label class="form-label">Vị trí</label><input id="edit_location" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Trạng thái</label><select id="edit_status" class="form-select"><option>OK</option><option>NG</option><option>Maintenance/Warranty</option></select></div>
      <div class="mb-2"><label class="form-label">Ngày nhập</label><input id="edit_import" class="form-control" type="date"></div>
      <div class="mb-2"><label class="form-label">Hạn bảo hành</label><input id="edit_warranty" class="form-control" type="date"></div>  
    </div>
  </div>
  <div class="modal-footer"><button class="btn btn-secondary" data-bs-dismiss="modal">Đóng</button><button class="btn btn-primary" onclick="doEdit()">Lưu</button></div>
</div></div></div>

<!-- Delete -->
<div class="modal" id="modalDelete" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
  <div class="modal-header"><h5 class="modal-title">Xóa tài sản</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
  <div class="modal-body"><input id="del_code" class="form-control" placeholder="Mã tài sản"></div>
  <div class="modal-footer"><button class="btn btn-secondary" data-bs-dismiss="modal">Đóng</button><button class="btn btn-danger" onclick="doDelete()">Xóa</button></div>
</div></div></div>

<!-- History -->
<div class="modal" id="modalHist" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
  <div class="modal-header"><h5 class="modal-title">Thêm lịch sử bảo hành</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
  <div class="modal-body">
    <div id="histAlert" class="alert alert-danger d-none"></div>
    <div class="mb-2"><label class="form-label">Mã tài sản</label><input id="hist_code" class="form-control"></div>
    <div class="mb-2"><label class="form-label">Lỗi</label><input id="hist_fault" class="form-control"></div>
    <div class="mb-2"><label class="form-label">Ngày gửi đi</label><input id="hist_sent" class="form-control" type="date"></div>
  </div>
  <div class="modal-footer"><button class="btn btn-secondary" data-bs-dismiss="modal">Đóng</button><button class="btn btn-primary" onclick="doAddHistory()">Lưu</button></div>
</div></div></div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
<script>
const addModal = new bootstrap.Modal(document.getElementById('modalAdd'));
const editModal = new bootstrap.Modal(document.getElementById('modalEdit'));
const delModal = new bootstrap.Modal(document.getElementById('modalDelete'));
const histModal = new bootstrap.Modal(document.getElementById('modalHist'));

function openAdd(){ document.getElementById('addAlert').classList.add('d-none'); addModal.show(); }
function openEdit(){ document.getElementById('editAlert').classList.add('d-none'); editModal.show(); }
function openDelete(){ delModal.show(); }
function openHist(){ document.getElementById('histAlert').classList.add('d-none'); histModal.show(); }

async function loadTable(){
  const res = await fetch('/api/assets'); 
  const list = await res.json();
  const tbody = document.getElementById('tbody'); 
  tbody.innerHTML = '';
  for(const a of list){
    const tr = document.createElement('tr');
    tr.innerHTML = `\
      <td>${a.index}</td>\
      <td class="code-link">${a.code}</td>\
      <td>${a.name}</td>\
      <td>${a.brand}</td>\
      <td>${a.description || ''}</td>\
      <td>${a.serial}</td>\
      <td>${a.coc || ''}</td>\
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
    code: document.getElementById('add_code').value.trim(),
    name: document.getElementById('add_name').value.trim(),
    brand: document.getElementById('add_brand').value.trim(),
    serial: document.getElementById('add_serial').value.trim(),
    location: document.getElementById('add_location').value.trim(),
    status: document.getElementById('add_status').value,
    import_date: document.getElementById('add_import').value,
    warranty_end: document.getElementById('add_warranty').value,
    description: document.getElementById('add_description').value.trim(),
    coc: document.getElementById('add_coc').value.trim()
  };
  const res = await fetch('/api/assets', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  const data = await res.json();
  if(!res.ok){
    const el = document.getElementById('addAlert'); el.classList.remove('d-none');
    if(data.missing_fields) el.innerText = data.error + ': ' + data.missing_fields.join(', '); else el.innerText = data.error || 'Có lỗi';
    return;
  }
  addModal.hide(); loadTable();
  ['add_code','add_name','add_brand','add_serial','add_location','add_import','add_warranty','add_description','add_coc'].forEach(id=>document.getElementById(id).value='');
}

async function loadForEdit(){
  const code = document.getElementById('edit_lookup_code').value.trim();
  if(!code){ document.getElementById('editAlert').classList.remove('d-none'); document.getElementById('editAlert').innerText='Nhập mã tài sản'; return; }
  const res = await fetch('/api/assets/' + encodeURIComponent(code));
  if(!res.ok){ const d = await res.json(); document.getElementById('editAlert').classList.remove('d-none'); document.getElementById('editAlert').innerText = d.error || 'Không tìm thấy'; return; }
  const a = await res.json();
  document.getElementById('edit_code').value = a.code;
  document.getElementById('edit_name').value = a.name;
  document.getElementById('edit_brand').value = a.brand;
  document.getElementById('edit_serial').value = a.serial;
  document.getElementById('edit_location').value = a.location;
  document.getElementById('edit_status').value = a.status;
  document.getElementById('edit_import').value = a.import_date;
  document.getElementById('edit_warranty').value = a.warranty_end;
  document.getElementById('edit_description').value = a.description || '';
  document.getElementById('edit_coc').value = a.coc || '';
  document.getElementById('editForm').style.display = 'block';
}

async function doEdit(){
  const code = document.getElementById('edit_code').value;
  const payload = {
    name: document.getElementById('edit_name').value.trim(),
    brand: document.getElementById('edit_brand').value.trim(),
    serial: document.getElementById('edit_serial').value.trim(),
    location: document.getElementById('edit_location').value.trim(),
    status: document.getElementById('edit_status').value,
    import_date: document.getElementById('edit_import').value,
    warranty_end: document.getElementById('edit_warranty').value,
    description: document.getElementById('edit_description').value.trim(),
    coc: document.getElementById('edit_coc').value.trim()
  };
  const res = await fetch('/api/assets/' + encodeURIComponent(code), {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  const data = await res.json();
  if(!res.ok){ if(data.missing_fields) { document.getElementById('editAlert').classList.remove('d-none'); document.getElementById('editAlert').innerText = data.error + ': ' + data.missing_fields.join(', '); } else { document.getElementById('editAlert').classList.remove('d-none'); document.getElementById('editAlert').innerText = data.error || 'Có lỗi'; } return; }
  editModal.hide(); loadTable(); document.getElementById('editForm').style.display='none'; document.getElementById('edit_lookup_code').value='';
}

async function doDelete(){
  const code = document.getElementById('del_code').value.trim();
  if(!code) return alert('Nhập mã để xóa');
  if(!confirm('Bạn có chắc muốn xóa ' + code + '?')) return;
  const res = await fetch('/api/assets/' + encodeURIComponent(code), {method:'DELETE'});
  const data = await res.json();
  if(!res.ok) return alert(data.error || 'Có lỗi');
  delModal.hide(); loadTable(); document.getElementById('del_code').value='';
}

async function doAddHistory(){
  const code = document.getElementById('hist_code').value.trim();
  const payload = { fault: document.getElementById('hist_fault').value.trim(), sent_date: document.getElementById('hist_sent').value };
  const res = await fetch('/api/assets/' + encodeURIComponent(code) + '/history', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  const data = await res.json();
  if(!res.ok){ const el = document.getElementById('histAlert'); el.classList.remove('d-none'); if(data.missing_fields) el.innerText = data.error + ': ' + data.missing_fields.join(', '); else el.innerText = data.error || 'Có lỗi'; return; }
  histModal.hide(); loadTable(); ['hist_code','hist_fault','hist_sent'].forEach(id=>document.getElementById(id).value='');
}

async function toggleHistory(row, code){
  let next = row.nextSibling; if(next && next.classList && next.classList.contains('history-row')){ next.remove(); return; }
  const res = await fetch('/api/assets/' + encodeURIComponent(code) + '/history'); const data = await res.json();
  const tr = document.createElement('tr'); tr.classList.add('history-row'); const td = document.createElement('td'); td.colSpan = 11;
  if(data.error || data.length === 0){ td.innerHTML = '<em>Chưa có lịch sử</em>'; }
  else{ let html = '<table class="table table-sm"><thead><tr><th>Lần</th><th>Lỗi</th><th>Ngày gửi</th></tr></thead><tbody>'; for(const h of data) html += `<tr><td>${h.seq}</td><td>${h.fault}</td><td>${h.sent_date}</td></tr>`; html += '</tbody></table>'; td.innerHTML = html; }
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
