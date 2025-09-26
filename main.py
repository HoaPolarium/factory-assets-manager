from flask import Flask, render_template_string, request, jsonify, send_file
import json, os, io
from openpyxl import Workbook
from datetime import datetime

app = Flask(__name__)
DATA_FILE = 'assets.json'

# --------- Data helpers ---------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"assets": []}
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --------- API routes ---------
@app.route('/')
def index():
    return render_template_string(TEMPLATE)

@app.route('/api/assets', methods=['GET'])
def api_get_assets():
    return jsonify(load_data()['assets'])

@app.route('/api/assets', methods=['POST'])
def api_add_asset():
    payload = request.get_json() or {}
    required = ["code","name","brand","serial","location","status","import_date","warranty_end"]
    missing = [k for k in required if not payload.get(k)]
    if missing:
        return jsonify({"error":"Thiếu thông tin","missing_fields": missing}), 400

    data = load_data()
    # check unique code
    if any(a['code'] == payload['code'] for a in data['assets']):
        return jsonify({"error":"Mã tài sản đã tồn tại"}), 400
    idx = len(data['assets']) + 1
    new = {
        'index': idx,
        'code': payload['code'],
        'name': payload['name'],
        'brand': payload['brand'],
        'serial': payload['serial'],
        'location': payload['location'],
        'status': payload['status'],
        'import_date': payload['import_date'],
        'warranty_end': payload['warranty_end'],
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
        return jsonify({"error":"Không tìm thấy mã tài sản"}), 404
    return jsonify(asset)

@app.route('/api/assets/<code>', methods=['PUT'])
def api_update_asset(code):
    payload = request.get_json() or {}
    required = ["name","brand","serial","location","status","import_date","warranty_end"]
    missing = [k for k in required if not payload.get(k)]
    if missing:
        return jsonify({"error":"Thiếu thông tin","missing_fields": missing}), 400

    data = load_data()
    asset = next((a for a in data['assets'] if a['code'] == code), None)
    if not asset:
        return jsonify({"error":"Không tìm thấy mã tài sản"}), 404
    # update fields (code not changed)
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
        return jsonify({"error":"Không tìm thấy mã tài sản"}), 404
    # reindex
    for i,a in enumerate(new_assets, start=1):
        a['index'] = i
    data['assets'] = new_assets
    save_data(data)
    return jsonify({"ok": True})

@app.route('/api/assets/<code>/history', methods=['GET'])
def api_get_history(code):
    data = load_data()
    asset = next((a for a in data['assets'] if a['code'] == code), None)
    if not asset:
        return jsonify({"error":"Không tìm thấy mã tài sản"}), 404
    return jsonify(asset.get('history', []))

@app.route('/api/assets/<code>/history', methods=['POST'])
def api_add_history(code):
    payload = request.get_json() or {}
    required = ["fault","sent_date","returned_date"]
    missing = [k for k in required if not payload.get(k)]
    if missing:
        return jsonify({"error":"Thiếu thông tin","missing_fields": missing}), 400
    data = load_data()
    asset = next((a for a in data['assets'] if a['code'] == code), None)
    if not asset:
        return jsonify({"error":"Không tìm thấy mã tài sản"}), 404
    seq = len(asset.get('history', [])) + 1
    entry = {
        'seq': seq,
        'fault': payload['fault'],
        'sent_date': payload['sent_date'],
        'returned_date': payload['returned_date']
    }
    asset.setdefault('history', []).append(entry)
    save_data(data)
    return jsonify(entry), 201

@app.route('/export/excel')
def export_excel():
    data = load_data()
    wb = Workbook()
    ws = wb.active
    ws.title = 'Assets'
    ws.append(["STT","Mã tài sản","Tên máy","Hãng","Serial","Vị trí","Trạng thái","Ngày nhập","Hạn bảo hành"])
    for a in data['assets']:
        ws.append([a['index'], a['code'], a['name'], a['brand'], a['serial'], a['location'], a['status'], a['import_date'], a['warranty_end']])
    ws2 = wb.create_sheet('History')
    ws2.append(["Mã tài sản","Lần","Lỗi","Ngày gửi đi","Ngày nhận về"])
    for a in data['assets']:
        for h in a.get('history', []):
            ws2.append([a['code'], h['seq'], h['fault'], h['sent_date'], h['returned_date']])
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    filename = f"assets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(stream, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# --------- Frontend template ---------
TEMPLATE = '''
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Quản lý tài sản</title>
  <style>
    body{font-family:Arial;background:#f0f4f8;padding:20px}
    h2{color:#1976d2}
    table{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 2px 6px rgba(0,0,0,0.08)}
    th,td{border:1px solid #e3e7ea;padding:8px;text-align:left}
    th{background:#1976d2;color:#fff}
    tr:hover{background:#f9fbff}
    .controls{margin-bottom:12px}
    .btn{padding:8px 12px;border-radius:6px;border:none;cursor:pointer;margin-right:6px}
    .btn-primary{background:#1976d2;color:#fff}
    .btn-danger{background:#d32f2f;color:#fff}
    .btn-secondary{background:#6c757d;color:#fff}
    .modal{display:none;position:fixed;left:0;top:0;right:0;bottom:0;background:rgba(0,0,0,0.4);align-items:center;justify-content:center}
    .modal .content{background:#fff;padding:16px;border-radius:8px;width:520px;max-width:95%}
    .form-row{margin-bottom:8px}
    label{display:block;margin-bottom:4px;font-size:13px}
    input[type=text], input[type=date]{width:100%;padding:8px;box-sizing:border-box}
  </style>
</head>
<body>
  <h2>Quản lý tài sản nhà máy</h2>
  <div class="controls">
    <button class="btn btn-primary" onclick="openModal('addModal')">Thêm thông tin tài sản</button>
    <button class="btn btn-secondary" onclick="openModal('editModal')">Sửa thông tin tài sản</button>
    <button class="btn btn-danger" onclick="openModal('deleteModal')">Xóa thông tin tài sản</button>
    <button class="btn" onclick="openModal('histModal')">Thêm lịch sử</button>
    <button class="btn" onclick="window.location='/export/excel'">Xuất Excel</button>
  </div>

  <table>
    <thead>
      <tr><th>STT</th><th>Mã tài sản</th><th>Tên máy</th><th>Hãng</th><th>Serial</th><th>Vị trí</th><th>Trạng thái</th><th>Ngày nhập</th><th>Hạn bảo hành</th></tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>

  <!-- Add Modal -->
  <div class="modal" id="addModal"><div class="content">
    <h3>Thêm sản phẩm</h3>
    <div class="form-row"><label>Mã tài sản</label><input id="add_code" type="text"></div>
    <div class="form-row"><label>Tên máy</label><input id="add_name" type="text"></div>
    <div class="form-row"><label>Hãng</label><input id="add_brand" type="text"></div>
    <div class="form-row"><label>Serial</label><input id="add_serial" type="text"></div>
    <div class="form-row"><label>Vị trí</label><input id="add_location" type="text"></div>
    <div class="form-row"><label>Trạng thái</label><input id="add_status" type="text"></div>
    <div class="form-row"><label>Ngày nhập</label><input id="add_import" type="date"></div>
    <div class="form-row"><label>Hạn bảo hành</label><input id="add_warranty" type="date"></div>
    <div style="text-align:right"><button class="btn btn-primary" onclick="doAdd()">Lưu</button> <button class="btn" onclick="closeModal('addModal')">Đóng</button></div>
  </div></div>

  <!-- Edit Modal -->
  <div class="modal" id="editModal"><div class="content">
    <h3>Sửa thông tin tài sản</h3>
    <div class="form-row"><label>Nhập mã tài sản để tải</label><input id="edit_code_load" type="text"> <button onclick="loadForEdit()" class="btn">Tải</button></div>
    <div id="editForm" style="display:none">
      <div class="form-row"><label>Mã tài sản (không sửa)</label><input id="edit_code" type="text" disabled></div>
      <div class="form-row"><label>Tên máy</label><input id="edit_name" type="text"></div>
      <div class="form-row"><label>Hãng</label><input id="edit_brand" type="text"></div>
      <div class="form-row"><label>Serial</label><input id="edit_serial" type="text"></div>
      <div class="form-row"><label>Vị trí</label><input id="edit_location" type="text"></div>
      <div class="form-row"><label>Trạng thái</label><input id="edit_status" type="text"></div>
      <div class="form-row"><label>Ngày nhập</label><input id="edit_import" type="date"></div>
      <div class="form-row"><label>Hạn bảo hành</label><input id="edit_warranty" type="date"></div>
      <div style="text-align:right"><button class="btn btn-primary" onclick="doEdit()">Lưu</button> <button class="btn" onclick="closeModal('editModal')">Đóng</button></div>
    </div>
  </div></div>

  <!-- Delete Modal -->
  <div class="modal" id="deleteModal"><div class="content">
    <h3>Xóa sản phẩm</h3>
    <div class="form-row"><label>Mã tài sản</label><input id="del_code" type="text"></div>
    <div style="text-align:right"><button class="btn btn-danger" onclick="doDelete()">Xóa</button> <button class="btn" onclick="closeModal('deleteModal')">Đóng</button></div>
  </div></div>

  <!-- History Modal -->
  <div class="modal" id="histModal"><div class="content">
    <h3>Thêm lịch sử</h3>
    <div class="form-row"><label>Mã tài sản</label><input id="hist_code" type="text"></div>
    <div class="form-row"><label>Lỗi</label><input id="hist_fault" type="text"></div>
    <div class="form-row"><label>Ngày gửi đi</label><input id="hist_sent" type="date"></div>
    <div class="form-row"><label>Ngày nhận về</label><input id="hist_return" type="date"></div>
    <div style="text-align:right"><button class="btn btn-primary" onclick="doAddHistory()">Lưu</button> <button class="btn" onclick="closeModal('histModal')">Đóng</button></div>
  </div></div>

<script>
function openModal(id){ document.getElementById(id).style.display='flex'; }
function closeModal(id){ document.getElementById(id).style.display='none'; if(id==='editModal'){ document.getElementById('editForm').style.display='none'; document.getElementById('edit_code_load').value=''; } }

// load assets list
async function loadTable(){
  let res = await fetch('/api/assets');
  let list = await res.json();
  let tbody = document.getElementById('tbody'); tbody.innerHTML='';
  for(let a of list){
    let tr = document.createElement('tr');
    tr.innerHTML = `<td>${a.index}</td><td class="code" style="color:#1976d2;cursor:pointer">${a.code}</td><td>${a.name}</td><td>${a.brand}</td><td>${a.serial}</td><td>${a.location}</td><td>${a.status}</td><td>${a.import_date}</td><td>${a.warranty_end}</td>`;
    tr.querySelector('.code').onclick = ()=> toggleHistory(tr, a.code);
    tbody.appendChild(tr);
  }
}

async function doAdd(){
  const payload = {
    code: document.getElementById('add_code').value.trim(),
    name: document.getElementById('add_name').value.trim(),
    brand: document.getElementById('add_brand').value.trim(),
    serial: document.getElementById('add_serial').value.trim(),
    location: document.getElementById('add_location').value.trim(),
    status: document.getElementById('add_status').value.trim(),
    import_date: document.getElementById('add_import').value,
    warranty_end: document.getElementById('add_warranty').value
  };
  let res = await fetch('/api/assets', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  let data = await res.json();
  if(!res.ok){
    if(data.missing_fields) alert(data.error + ': ' + data.missing_fields.join(', '));
    else alert(data.error || 'Có lỗi xảy ra');
    return;
  }
  alert('Thêm thành công'); closeModal('addModal'); loadTable();
}

async function loadForEdit(){
  const code = document.getElementById('edit_code_load').value.trim();
  if(!code){ alert('Nhập mã tài sản cần sửa'); return; }
  let res = await fetch('/api/assets/' + encodeURIComponent(code));
  if(!res.ok){ alert((await res.json()).error || 'Không tìm thấy'); return; }
  let a = await res.json();
  document.getElementById('edit_code').value = a.code;
  document.getElementById('edit_name').value = a.name;
  document.getElementById('edit_brand').value = a.brand;
  document.getElementById('edit_serial').value = a.serial;
  document.getElementById('edit_location').value = a.location;
  document.getElementById('edit_status').value = a.status;
  document.getElementById('edit_import').value = a.import_date;
  document.getElementById('edit_warranty').value = a.warranty_end;
  document.getElementById('editForm').style.display='block';
}

async function doEdit(){
  const code = document.getElementById('edit_code').value;
  const payload = {
    name: document.getElementById('edit_name').value.trim(),
    brand: document.getElementById('edit_brand').value.trim(),
    serial: document.getElementById('edit_serial').value.trim(),
    location: document.getElementById('edit_location').value.trim(),
    status: document.getElementById('edit_status').value.trim(),
    import_date: document.getElementById('edit_import').value,
    warranty_end: document.getElementById('edit_warranty').value
  };
  let res = await fetch('/api/assets/' + encodeURIComponent(code), {method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  let data = await res.json();
  if(!res.ok){ if(data.missing_fields) alert(data.error + ': ' + data.missing_fields.join(', ')); else alert(data.error || 'Có lỗi'); return; }
  alert('Cập nhật thành công'); closeModal('editModal'); loadTable();
}

async function doDelete(){
  const code = document.getElementById('del_code').value.trim();
  if(!code){ alert('Nhập mã để xóa'); return; }
  if(!confirm('Bạn chắc chắn muốn xóa tài sản ' + code + '?')) return;
  let res = await fetch('/api/assets/' + encodeURIComponent(code), {method:'DELETE'});
  let data = await res.json();
  if(!res.ok){ alert(data.error || 'Có lỗi'); return; }
  alert('Xóa thành công'); closeModal('deleteModal'); loadTable();
}

async function doAddHistory(){
  const code = document.getElementById('hist_code').value.trim();
  const payload = { fault: document.getElementById('hist_fault').value.trim(), sent_date: document.getElementById('hist_sent').value, returned_date: document.getElementById('hist_return').value };
  if(!code){ alert('Nhập mã tài sản'); return; }
  let res = await fetch('/api/assets/' + encodeURIComponent(code) + '/history', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  let data = await res.json();
  if(!res.ok){ if(data.missing_fields) alert(data.error + ': ' + data.missing_fields.join(', ')); else alert(data.error || 'Có lỗi'); return; }
  alert('Thêm lịch sử thành công'); closeModal('histModal'); loadTable();
}

async function toggleHistory(tr, code){
  let next = tr.nextSibling;
  if(next && next.classList && next.classList.contains('history-row')){ next.remove(); return; }
  let res = await fetch('/api/assets/' + encodeURIComponent(code) + '/history');
  let data = await res.json();
  let histTr = document.createElement('tr'); histTr.classList.add('history-row');
  let td = document.createElement('td'); td.colSpan = 9;
  if(data.error || data.length === 0){ td.innerHTML = '<em>Chưa có lịch sử</em>'; }
  else{
    let html = '<table style="width:100%;border-collapse:collapse"><tr><th>Lần</th><th>Lỗi</th><th>Ngày gửi</th><th>Ngày nhận</th></tr>';
    for(let h of data){ html += `<tr><td>${h.seq}</td><td>${h.fault}</td><td>${h.sent_date}</td><td>${h.returned_date}</td></tr>`; }
    html += '</table>';
    td.innerHTML = html;
  }
  histTr.appendChild(td); tr.parentNode.insertBefore(histTr, tr.nextSibling);
}

// init
loadTable();
</script>
</body>
</html>
'''

if __name__ == '__main__':
    print('Server running at http://127.0.0.1:5000')
    app.run(debug=True)