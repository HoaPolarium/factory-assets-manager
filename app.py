# app.py
from flask import Flask, request, jsonify, render_template_string, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_
import os, io
from datetime import datetime, date
from openpyxl import Workbook

####################
# Configuration
####################
app = Flask(__name__)
# use DATABASE_URL env var if present, otherwise sqlite file
DATABASE_URL = os.environ.get('DATABASE_URL') or os.environ.get('SQLALCHEMY_DATABASE_URI') or 'sqlite:///assets.db'
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

####################
# Models
####################
class Asset(db.Model):
    __tablename__ = 'assets'
    id = db.Column(db.Integer, primary_key=True)           # internal id
    idx = db.Column(db.Integer, nullable=False)            # STT (index)
    clc = db.Column(db.String(200), nullable=True)
    code = db.Column(db.String(200), nullable=False, unique=True)
    name = db.Column(db.String(500), nullable=False)
    brand = db.Column(db.String(200), nullable=True)
    model = db.Column(db.String(200), nullable=True)
    description = db.Column(db.Text, nullable=True)
    serial = db.Column(db.String(200), nullable=True)
    location = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(100), nullable=True)
    import_date = db.Column(db.Date, nullable=True)
    warranty_end = db.Column(db.Date, nullable=True)
    history = db.relationship('History', backref='asset', cascade='all, delete-orphan', lazy='joined', order_by="History.id")

    def to_dict(self):
        return {
            'id': self.id,
            'index': self.idx,
            'clc': self.clc or '',
            'code': self.code,
            'name': self.name,
            'brand': self.brand or '',
            'model': self.model or '',
            'description': self.description or '',
            'serial': self.serial or '',
            'location': self.location or '',
            'status': self.status or '',
            'import_date': self.import_date.strftime('%Y-%m-%d') if self.import_date else '',
            'warranty_end': self.warranty_end.strftime('%Y-%m-%d') if self.warranty_end else '',
            'history': [h.to_dict() for h in sorted(self.history, key=lambda x: (x.type, x.seq) )]
        }

class History(db.Model):
    __tablename__ = 'history'
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'fault' or 'calib'
    seq = db.Column(db.Integer, nullable=False)      # sequence per type for that asset
    # fault fields
    fault = db.Column(db.String(500), nullable=True)
    fault_date = db.Column(db.Date, nullable=True)
    sent_date = db.Column(db.Date, nullable=True)
    return_date = db.Column(db.Date, nullable=True)
    # calib fields
    calib_date = db.Column(db.Date, nullable=True)
    expire_date = db.Column(db.Date, nullable=True)

    def to_dict(self):
        d = {'type': self.type, 'seq': self.seq}
        if self.type == 'fault':
            d.update({
                'fault': self.fault or '',
                'fault_date': self.fault_date.strftime('%Y-%m-%d') if self.fault_date else '',
                'sent_date': self.sent_date.strftime('%Y-%m-%d') if self.sent_date else '',
                'return_date': self.return_date.strftime('%Y-%m-%d') if self.return_date else ''
            })
        else:
            d.update({
                'calib_date': self.calib_date.strftime('%Y-%m-%d') if self.calib_date else '',
                'expire_date': self.expire_date.strftime('%Y-%m-%d') if self.expire_date else ''
            })
        return d

####################
# Helpers
####################
def parse_date(d):
    if not d:
        return None
    if isinstance(d, date):
        return d
    try:
        return datetime.strptime(d, '%Y-%m-%d').date()
    except Exception:
        return None

def recompute_indexes():
    """Recompute idx (STT) for all assets ordered by id ascending."""
    assets = Asset.query.order_by(Asset.id).all()
    for i, a in enumerate(assets, start=1):
        a.idx = i
    db.session.commit()

def find_asset_by_identifier_value(identifier):
    if not identifier:
        return None
    id_norm = identifier.strip()
    # search case-insensitive for code/clc/serial
    return Asset.query.filter(
        or_(
            func.lower(Asset.code) == id_norm.lower(),
            func.lower(Asset.clc) == id_norm.lower(),
            func.lower(Asset.serial) == id_norm.lower()
        )
    ).first()

####################
# API endpoints
####################

@app.route('/api/assets', methods=['GET'])
def api_list_assets():
    assets = Asset.query.order_by(Asset.idx).all()
    return jsonify([a.to_dict() for a in assets])

@app.route('/api/assets', methods=['POST'])
def api_add_asset():
    payload = request.get_json() or {}
    required = ['clc','code','name','brand','model','serial','location','status','import_date','warranty_end','description']
    missing = [k for k in required if not payload.get(k) and payload.get(k) != '']
    # note: we accept empty-string for description; but other fields require at least ''
    # Use your original logic: disallow missing (empty)
    missing = [k for k in required if not payload.get(k)]
    if missing:
        return jsonify({'error':'Thiếu thông tin','missing_fields': missing}), 400
    if Asset.query.filter_by(code=payload['code']).first():
        return jsonify({'error':'Mã tài sản đã tồn tại'}), 400
    # create asset
    last_idx = db.session.query(func.max(Asset.idx)).scalar() or 0
    a = Asset(
        idx = (last_idx or 0) + 1,
        clc = payload.get('clc',''),
        code = payload.get('code',''),
        name = payload.get('name',''),
        brand = payload.get('brand',''),
        model = payload.get('model',''),
        description = payload.get('description',''),
        serial = payload.get('serial',''),
        location = payload.get('location',''),
        status = payload.get('status',''),
        import_date = parse_date(payload.get('import_date')),
        warranty_end = parse_date(payload.get('warranty_end'))
    )
    db.session.add(a)
    db.session.commit()
    return jsonify(a.to_dict()), 201

@app.route('/api/assets/<code>', methods=['GET'])
def api_get_asset(code):
    a = Asset.query.filter_by(code=code).first()
    if not a:
        return jsonify({'error':'Không tìm thấy mã tài sản'}), 404
    return jsonify(a.to_dict())

@app.route('/api/assets/<code>', methods=['PUT'])
def api_update_asset(code):
    payload = request.get_json() or {}
    required = ['clc','name','brand','model','description','serial','location','status','import_date','warranty_end']
    missing = [k for k in required if not payload.get(k)]
    if missing:
        return jsonify({'error':'Thiếu thông tin','missing_fields': missing}), 400
    a = Asset.query.filter_by(code=code).first()
    if not a:
        return jsonify({'error':'Không tìm thấy mã tài sản'}), 404
    a.clc = payload.get('clc','')
    a.name = payload.get('name','')
    a.brand = payload.get('brand','')
    a.model = payload.get('model','')
    a.description = payload.get('description','')
    a.serial = payload.get('serial','')
    a.location = payload.get('location','')
    a.status = payload.get('status','')
    a.import_date = parse_date(payload.get('import_date'))
    a.warranty_end = parse_date(payload.get('warranty_end'))
    db.session.commit()
    return jsonify(a.to_dict())

@app.route('/api/assets', methods=['DELETE'])
def api_delete_asset_by_identifier():
    identifier = request.args.get('identifier', '').strip()
    if not identifier and request.is_json:
        body = request.get_json()
        identifier = (body.get('identifier') or '').strip() if isinstance(body, dict) else ''
    if not identifier:
        return jsonify({'error':'Thiếu identifier để xóa (code/clc/serial)'}), 400
    a = find_asset_by_identifier_value(identifier)
    if not a:
        return jsonify({'error':'Không tìm thấy tài sản phù hợp'}), 404
    db.session.delete(a)
    db.session.commit()
    recompute_indexes()
    return jsonify({'ok': True})

@app.route('/api/assets/<code>/history', methods=['GET'])
def api_get_history(code):
    a = Asset.query.filter_by(code=code).first()
    if not a:
        return jsonify({'error':'Không tìm thấy mã tài sản'}), 404
    return jsonify([h.to_dict() for h in sorted(a.history, key=lambda x: (x.type, x.seq))])

@app.route('/api/assets/history', methods=['GET'])
def api_get_history_by_identifier():
    identifier = request.args.get('identifier', '').strip()
    if not identifier:
        return jsonify({'error':'Thiếu identifier'}), 400
    a = find_asset_by_identifier_value(identifier)
    if not a:
        return jsonify({'error':'Không tìm thấy mã tài sản'}), 404
    return jsonify([h.to_dict() for h in sorted(a.history, key=lambda x: (x.type, x.seq))])

@app.route('/api/assets/<code>/history', methods=['POST'])
def api_add_history(code):
    payload = request.get_json() or {}
    payload['identifier'] = code
    return _handle_add_history(payload)

@app.route('/api/assets/history', methods=['POST'])
def api_add_history_by_identifier():
    payload = request.get_json() or {}
    return _handle_add_history(payload)

def _handle_add_history(payload):
    identifier = (payload.get('identifier') or '').strip()
    payload_type = payload.get('type')
    if not identifier:
        return jsonify({'error':'Thiếu identifier (code/clc/serial)'}), 400
    if payload_type not in ('fault','calib'):
        return jsonify({'error':'Thiếu hoặc sai type (phải là "fault" hoặc "calib")'}), 400
    a = find_asset_by_identifier_value(identifier)
    if not a:
        return jsonify({'error':'Không tìm thấy mã tài sản'}), 404

    if payload_type == 'fault':
        required = ['fault','fault_date','sent_date']
        missing = [k for k in required if not payload.get(k)]
        if missing:
            return jsonify({'error':'Thiếu thông tin cho fault','missing_fields': missing}), 400
        seq = db.session.query(func.count(History.id)).filter_by(asset_id=a.id, type='fault').scalar() or 0
        seq = seq + 1
        h = History(
            asset_id = a.id,
            type='fault',
            seq=seq,
            fault=payload.get('fault',''),
            fault_date=parse_date(payload.get('fault_date')),
            sent_date=parse_date(payload.get('sent_date')),
            return_date=parse_date(payload.get('return_date') or None)
        )
        db.session.add(h)
        db.session.commit()
        return jsonify(h.to_dict()), 201

    else:  # calib
        required = ['calib_date','expire_date']
        missing = [k for k in required if not payload.get(k)]
        if missing:
            return jsonify({'error':'Thiếu thông tin cho calib','missing_fields': missing}), 400
        seq = db.session.query(func.count(History.id)).filter_by(asset_id=a.id, type='calib').scalar() or 0
        seq = seq + 1
        h = History(
            asset_id = a.id,
            type='calib',
            seq=seq,
            calib_date=parse_date(payload.get('calib_date')),
            expire_date=parse_date(payload.get('expire_date'))
        )
        db.session.add(h)

        # update asset status depending on expiry (same logic as before)
        latest_calib_date = h.calib_date
        # find latest calib by calib_date
        db.session.flush()  # ensure h has id if needed
        all_calibs = History.query.filter_by(asset_id=a.id, type='calib').all()
        latest = None
        latest_cd = None
        for c in all_calibs:
            if c.calib_date:
                if latest is None or c.calib_date > latest_cd:
                    latest = c
                    latest_cd = c.calib_date
        # consider the new one too
        if latest is None or (h.calib_date and h.calib_date > latest_cd):
            latest = h
            latest_cd = h.calib_date

        if latest and latest.expire_date:
            today = date.today()
            if today > latest.expire_date:
                a.status = 'Calib'   # as your logic requested (you can change string)
        db.session.commit()
        return jsonify(h.to_dict()), 201

@app.route('/export/excel', methods=['GET'])
def export_excel():
    assets = Asset.query.order_by(Asset.idx).all()
    wb = Workbook()
    ws = wb.active; ws.title = 'Assets'
    ws.append(['STT','Số CLC','Mã tài sản','Tên máy','Hãng','Model','Mô tả','Serial','Vị trí','Trạng thái','Ngày nhập','Hạn bảo hành'])
    for a in assets:
        ws.append([a.idx, a.clc or '', a.code, a.name, a.brand or '', a.model or '', a.description or '', a.serial or '', a.location or '', a.status or '', a.import_date.strftime('%Y-%m-%d') if a.import_date else '', a.warranty_end.strftime('%Y-%m-%d') if a.warranty_end else ''])
    ws2 = wb.create_sheet('History')
    ws2.append(['Mã tài sản','Loại','Lần','Tên lỗi/ngày calib','Ngày lỗi/Ngày calib','Ngày gửi đi','Ngày nhận về','Ngày hết hạn'])
    for a in assets:
        for h in sorted(a.history, key=lambda x: (x.type, x.seq)):
            if h.type == 'fault':
                ws2.append([a.code, 'fault', h.seq, h.fault or '', h.fault_date.strftime('%Y-%m-%d') if h.fault_date else '', h.sent_date.strftime('%Y-%m-%d') if h.sent_date else '', h.return_date.strftime('%Y-%m-%d') if h.return_date else '', ''])
            else:
                ws2.append([a.code, 'calib', h.seq, '', h.calib_date.strftime('%Y-%m-%d') if h.calib_date else '', '', '', h.expire_date.strftime('%Y-%m-%d') if h.expire_date else ''])
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

####################
# Startup: create tables if not exist
####################
with app.app_context():
    db.create_all()
    # ensure idx values exist for existing rows
    recompute_indexes()

if __name__ == '__main__':
    print('Run server at http://127.0.0.1:5000, DB =', DATABASE_URL)
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
