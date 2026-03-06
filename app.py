# app.py
"""
Flask app: Assets management using Supabase (compatible with Supabase Python Client v2)
- Fixed STT (index_num) behavior:
  * ensures index_num is generated on insert
  * fixes missing/null index_num by reindexing before listing
  * reindexes after delete
- UI is embedded (same as your UI, serial-click opens history)
"""

import os
import tempfile
from datetime import datetime, date
from flask import Flask, request, jsonify, render_template_string, send_file
from supabase import create_client
import openpyxl
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

app = Flask(__name__)

# Giới hạn upload: 5MB
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Please set SUPABASE_URL and SUPABASE_KEY environment variables")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------
# Helpers
# -----------------------

def transform_asset_for_frontend(a):
    """Map DB asset to frontend shape. index is added in api_list_assets."""
    if not a:
        return a
    return dict(a)

def normalize_dates(data):
    for field in [
      "fault_date", "sent_date", "return_date",
      "calib_date", "expire_date",
      "import_date", "warranty_end",
      "declaration_date",
      "invoice_date"
    ]:
        if field in data and data[field] == "":
            data[field] = None
    return data

# -----------------------
# Routes (API + UI)
# -----------------------

# Embedded UI (kept same as earlier; clicking serial shows history)
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
    body { 
      overflow: hidden;  
    }

    .table-scroll {
      max-height: 75vh;
      overflow-y: auto;
      overflow-x: auto;
    }

    /* Cố định header và hàng filter */
    #assetTable thead tr:first-child th {
      position: sticky;
      top: 0;
      background: white;
      z-index: 20;
    }

    /* Sticky filter row ngay dưới header */
    #assetTable thead tr.filter-row th {
      position: sticky;
      top: 48px;       /* ⇠ chỉnh theo chiều cao header thật */
      background: white;
      z-index: 19;
    }

    /* Giữ bảng không collapse để sticky không bị lệch */
    #assetTable {
      border-collapse: separate;
    }


    th.sortable {
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
      position: relative;
      padding-right: 18px !important;
    }

    .sort-icon {
      font-size: 11px;
      opacity: 0.35;
      margin-left: 4px;
    }

    .sort-icon.active {
      opacity: 1;
      font-weight: bold;
    }
                                                              
  </style>
</head>
<body>
<div class="container-fluid">
  <div class="d-flex justify-content-between align-items-center mb-3">   
    <div>
      <h3 class="mb-0">Quản lý tài sản</h3>
      <div id="totalAssets" class="text-muted mt-1" style="font-size:14px"></div>
      <div id="filteredAssets" class="text-muted" style="font-size:14px"></div>
    </div>
    <div>
      <button class="btn btn-success me-1" onclick="openAdd()">Thêm tài sản</button>
      <button class="btn btn-danger me-1" onclick="openDelete()">Xóa tài sản</button>
      <button class="btn btn-outline-primary" onclick="openHist()">Thêm lịch sử tài sản</button>
      <a class="btn btn-outline-success ms-2" href="/export/excel">Xuất Excel</a>
    </div>
  </div>


  <div class="card p-3">
    <div class="table-scroll">
      <table id="assetTable" class="table table-striped table-bordered align-middle">
        <thead>
          <tr>
              <th width="40"></th>
              <th class="sortable">Số CLC <span class="sort-icon">↕</span></th>
              <th class="sortable">Mã tài sản <span class="sort-icon">↕</span></th>
              <th class="sortable">Số tờ khai <span class="sort-icon">↕</span></th>
              <th class="sortable">Ngày tờ khai <span class="sort-icon">↕</span></th>
              <th class="sortable">Số invoice <span class="sort-icon">↕</span></th>
              <th class="sortable">Ngày hóa đơn <span class="sort-icon">↕</span></th>
              <th class="sortable">Nhà cung cấp <span class="sort-icon">↕</span></th>
              <th class="sortable">Tên máy <span class="sort-icon">↕</span></th>
              <th class="sortable">Hãng <span class="sort-icon">↕</span></th>
              <th class="sortable">Model <span class="sort-icon">↕</span></th>
              <th class="sortable">Mô tả <span class="sort-icon">↕</span></th>
              <th class="sortable">Serial <span class="sort-icon">↕</span></th>
              <th class="sortable">Vị trí <span class="sort-icon">↕</span></th>
              <th class="sortable">Trạng thái <span class="sort-icon">↕</span></th>
              <th class="sortable">Ngày nhập <span class="sort-icon">↕</span></th>
              <th class="sortable">Hạn bảo hành <span class="sort-icon">↕</span></th>
              <th class="sortable">Hiệu lực bảo hành <span class="sort-icon">↕</span></th>
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
              <th><input data-col="12" oninput="applyFilters()"></th>
              <th><input data-col="13" oninput="applyFilters()"></th>
              <th><input data-col="14" oninput="applyFilters()"></th>
              <th><input data-col="15" oninput="applyFilters()"></th>
              <th><input data-col="16" oninput="applyFilters()"></th>
          </tr>
        </thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- Modals (Add/Edit/Delete/History) - unchanged except Add will mark required fields with * -->
<!-- Add -->
<div class="modal" id="modalAdd" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
  <div class="modal-header"><h5 class="modal-title">Thêm sản phẩm</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
  <div class="modal-body">
    <div id="addAlert" class="alert alert-danger d-none"></div>
    <div class="mb-2"><label class="form-label">Số CLC</label><input id="add_clc" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Mã tài sản</label><input id="add_code" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Số tờ khai</label><input id="add_declaration_no" class="form-control"></div>
    <div class="mb-2"><label class="form-label">Ngày tờ khai</label><input id="add_declaration_date" type="date" class="form-control"></div>
    <div class="mb-2"><label class="form-label">Số invoice *</label><input id="add_invoice_no" class="form-control"></div>
    <div class="mb-2"><label class="form-label">Ngày hóa đơn</label><input id="add_invoice_date" type="date" class="form-control"></div>
    <div class="mb-2"><label class="form-label">Nhà cung cấp</label><input id="add_supplier" class="form-control"></div>
    <div class="mb-2"><label class="form-label">Tên máy</label><input id="add_name" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Hãng</label><input id="add_brand" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Model</label><input id="add_model" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Mô tả</label><input id="add_description" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Serial *</label><input id="add_serial" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Vị trí</label><input id="add_location" class="form-control" type="text"></div>
    <div class="mb-2"><label class="form-label">Trạng thái</label>
      <select id="add_status" class="form-select">
        <option>OK</option><option>NG</option><option>Maintenance/Warranty</option><option>Calib</option><option>Scrap</option>
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
    <div id="editForm" style="display:none">
      <div class="mb-2"><label class="form-label">Mã tài sản</label><input id="edit_code" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Số tờ khai</label><input id="edit_declaration_no" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Ngày tờ khai</label><input id="edit_declaration_date" type="date" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Số invoice</label><input id="edit_invoice_no" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Ngày hóa đơn</label><input id="edit_invoice_date" type="date" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Nhà cung cấp</label><input id="edit_supplier" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Số CLC</label><input id="edit_clc" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Tên máy</label><input id="edit_name" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Hãng</label><input id="edit_brand" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Model</label><input id="edit_model" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Mô tả</label><input id="edit_description" class="form-control" type="text"></div>
      <div class="mb-2"><label class="form-label">Serial</label><input id="edit_serial" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Vị trí</label><input id="edit_location" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Trạng thái</label><select id="edit_status" class="form-select"><option>OK</option><option>NG</option><option>Maintenance/Warranty</option><option>Calib</option><option>Scrap</option></select></div>
      <div class="mb-2"><label class="form-label">Ngày nhập</label><input id="edit_import" class="form-control" type="date"></div>
      <div class="mb-2"><label class="form-label">Hạn bảo hành</label><input id="edit_warranty" class="form-control" type="date"></div>  
    </div>
  </div>
  <div class="modal-footer"><button class="btn btn-secondary" data-bs-dismiss="modal">Đóng</button><button class="btn btn-primary" onclick="doEdit()">Lưu</button></div>
</div></div></div>

<!-- Delete -->
<div class="modal" id="modalDelete" tabindex="-1"><div class="modal-dialog"><div class="modal-content">
  <div class="modal-header"><h5 class="modal-title">Xóa tài sản</h5><button class="btn-close" data-bs-dismiss="modal"></button></div>
  <div class="mb-2">
    <label class="form-label">Serial</label>
    <input id="del_serial" class="form-control" placeholder="Nhập Serial">
  </div>

  <div class="mb-2">
    <label class="form-label">Số Invoice</label>
    <input id="del_invoice" class="form-control" placeholder="Nhập Số invoice">
  </div>
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
      <div class="mb-2"><label class="form-label">Tên lỗi*</label><input id="hist_fault" class="form-control"></div>
      <div class="mb-2"><label class="form-label">Ngày lỗi*</label><input id="hist_fault_date" class="form-control" type="date"></div>
      <div class="mb-2"><label class="form-label">Ngày gửi đi</label><input id="hist_sent" class="form-control" type="date"></div>
      <div class="mb-2"><label class="form-label">Ngày nhận về</label><input id="hist_return" class="form-control" type="date"></div>
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
let assetCache = [];

function openAdd(){ document.getElementById('addAlert').classList.add('d-none'); addModal.show(); }
function openEdit(){ document.getElementById('editAlert').classList.add('d-none'); editModal.show(); }
function openDelete(){ delModal.show(); }
function openHist(){ document.getElementById('histAlert').classList.add('d-none'); document.getElementById('hist_found').innerText=''; hist_target_identifier = null; histModal.show(); }

function updateFilteredAssets(){
  const table = document.getElementById('assetTable');
  const rows = table.tBodies[0].rows;

  let count = 0;
  for (const r of rows){
    if (!r.classList.contains("history-row") && r.style.display !== "none") {
      count++;
    }
  }

  document.getElementById("filteredAssets").innerText =
      "Số tài sản đang được lọc: " + count;
}

async function loadTable(){
  const res = await fetch("/api/assets");
  assetCache = await res.json();
  renderTable(assetCache);
  updateTotalAssets();
  updateFilteredAssets();
}

function updateTotalAssets(){
  const total = assetCache.length;
  document.getElementById("totalAssets").innerText =
      "Tổng số tài sản: " + total;
}

function renderTable(list){
  const tbody = document.querySelector("#assetTable tbody");
  tbody.innerHTML = "";
  for(const a of list){
    tbody.appendChild(renderRow(a));
  }
}

function renderRow(a){
  const tr = document.createElement("tr");
  tr.style.cursor = "pointer";
  tr.addEventListener("click", function(e){
    // tránh click vào button bên trong history
    if(e.target.closest("span")) return;
    if(e.target.tagName === "BUTTON") return;
    toggleHistory(tr, a.serial);
  });

  tr.dataset.id = a.id;
  tr.dataset.serial = a.serial || "";

  // Tính hiệu lực bảo hành
  let statusWarranty = "";
  const today = new Date();

  if (a.warranty_end) {
    const d = new Date(a.warranty_end);

    if (!isNaN(d.getTime())) {
      // Có giá trị hợp lệ
      statusWarranty = d >= today ? "Còn hạn" : "Hết hạn";
    } else {
      // Không parse được ngày → để rỗng
      statusWarranty = "";
    }
  } else {
    // Không có ngày bảo hành → để rỗng
    statusWarranty = "";
  }


  tr.innerHTML = `
    <td style="text-align:center">
      <span style="cursor:pointer;font-size:16px"
        onclick="openEditFromRow(${a.id})">🔧</span>
    </td>

    <td>${a.clc || ""}</td>
    <td>${a.code || ""}</td>
    <td>${a.declaration_no || ""}</td>
    <td>${a.declaration_date || ""}</td>
    <td>${a.invoice_no || ""}</td>
    <td>${a.invoice_date || ""}</td>
    <td>${a.supplier || ""}</td>
    <td>${a.name || ""}</td>
    <td>${a.brand || ""}</td>
    <td>${a.model || ""}</td>
    <td>${a.description || ""}</td>
    <td>${a.serial || ""}</td>
    <td>${a.location || ""}</td>
    <td>${a.status || ""}</td>
    <td>${a.import_date || ""}</td>
    <td>${a.warranty_end || ""}</td>
    <td style="font-weight:600; color:${statusWarranty === "Còn hạn" ? "green" : "red"}">${statusWarranty}</td>
  `;

  return tr;
}

function updateRowById(id, updated){

  const tr = document.querySelector(`#assetTable tr[data-id="${id}"]`);

  if(!tr) return;

  const newRow = renderRow(updated);

  tr.innerHTML = newRow.innerHTML;

  // update dataset
  tr.dataset.serial = updated.serial || "";
}

function appendRow(a){
  const tbody = document.querySelector("#assetTable tbody");
  tbody.appendChild(renderRow(a));
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
    updateFilteredAssets();
  }
}

let sortState = {}; // lưu trạng thái sort từng cột

function updateSortIcons(columnIndex, state) {
  const icons = document.querySelectorAll("#assetTable thead tr:first-child th .sort-icon");
  icons.forEach(i => {
    i.classList.remove("active");
    i.textContent = "↕"; // reset
  });

  const currentIcon = document.querySelector(`#assetTable thead tr:first-child th:nth-child(${columnIndex + 1}) .sort-icon`);
  if (!currentIcon) return;

  if (state === "asc") {
    currentIcon.textContent = "A↓Z";
    currentIcon.classList.add("active");
  }
  else if (state === "desc") {
    currentIcon.textContent = "Z↑A";
    currentIcon.classList.add("active");
  }
}

const columnMap = [
  "clc",
  "code",
  "declaration_no",
  "declaration_date",
  "invoice_no",
  "invoice_date",
  "supplier",
  "name",
  "brand",
  "model",
  "description",
  "serial",
  "location",
  "status",
  "import_date",
  "warranty_end",
  null
];

function sortTable(columnIndex) {
  const field = columnMap[columnIndex];
  if (!field) return; // cột không sort

  const state = sortState[columnIndex] || "none";
  const newState = state === "none" ? "asc" : state === "asc" ? "desc" : "none";
  sortState[columnIndex] = newState;

  updateSortIcons(columnIndex, newState);

  let data = [...assetCache];

  if (newState !== "none") {
    data.sort((a, b) => {
      const valA = a[field] || "";
      const valB = b[field] || "";

      // Ngày → sort đúng dạng date
      if (field === "import_date" || field === "warranty_end") {
        return newState === "asc"
          ? new Date(valA) - new Date(valB)
          : new Date(valB) - new Date(valA);
      }

      // Mặc định A-Z
      return newState === "asc"
        ? String(valA).localeCompare(String(valB), "vi")
        : String(valB).localeCompare(String(valA), "vi");
    });
  }

  renderTable(data);
  applyFilters();
  updateFilteredAssets();
}


function initSorting() {
  const headers = document.querySelectorAll("#assetTable thead tr:first-child th.sortable");
  headers.forEach((th, index) => {
    th.addEventListener("click", () => sortTable(index));
  });
}

function formatFileSize(bytes) {
  if (!bytes) return "";
  const kb = bytes / 1024;
  if (kb < 1024) return kb.toFixed(1) + " KB";
  return (kb / 1024).toFixed(2) + " MB";
}

function openEditFromRow(id){

  const a = assetCache.find(x => x.id === id);
  if(!a){
    alert("Không tìm thấy asset");
    return;
  }
  document.getElementById('edit_serial').dataset.assetId = id;

  if(!a){
    alert("Không tìm thấy asset");
    return;
  }

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

  // nếu bạn có các field mới
  if(document.getElementById('edit_invoice_no'))
    document.getElementById('edit_invoice_no').value = a.invoice_no || '';

  if(document.getElementById('edit_declaration_no'))
    document.getElementById('edit_declaration_no').value = a.declaration_no || '';

  if(document.getElementById('edit_supplier'))
    document.getElementById('edit_supplier').value = a.supplier || '';

  document.getElementById('editForm').style.display = 'block';

  editModal.show();
}

async function doAdd(){
  const payload = {
    clc: document.getElementById('add_clc').value.trim(),
    code: document.getElementById('add_code').value.trim(),
    declaration_no: document.getElementById('add_declaration_no').value.trim(),
    declaration_date: document.getElementById('add_declaration_date').value,
    invoice_no: document.getElementById('add_invoice_no').value.trim(),
    invoice_date: document.getElementById('add_invoice_date').value,
    supplier: document.getElementById('add_supplier').value.trim(),
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
  appendRow(data);     // thêm dòng mới
  assetCache.push(data);  // cập nhật cache
  updateTotalAssets();
  addModal.hide();
  ['add_clc','add_code','add_name','add_brand','add_model','add_serial','add_location','add_import','add_warranty','add_description'].forEach(id=>document.getElementById(id).value='');
}


async function doEdit() {

  const assetId = document.getElementById('edit_serial').dataset.assetId;

  const payload = {
    clc: document.getElementById('edit_clc').value.trim(),
    code: document.getElementById('edit_code').value.trim(),
    declaration_no: document.getElementById('edit_declaration_no').value.trim(),
    declaration_date: document.getElementById('edit_declaration_date').value,
    invoice_no: document.getElementById('edit_invoice_no').value.trim(),
    invoice_date: document.getElementById('edit_invoice_date').value,
    supplier: document.getElementById('edit_supplier').value.trim(),
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

  const res = await fetch('/api/assets/' + assetId, {
    method:'PUT',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify(payload)
  });

  const data = await res.json();

  if (!res.ok) {
    const alert = document.getElementById('editAlert');
    alert.classList.remove('d-none');
    alert.innerText = data.error || "Có lỗi khi cập nhật";
    return;
  }

  updateRowById(assetId, data);

  const idx = assetCache.findIndex(a => a.id == assetId);
  if (idx !== -1) assetCache[idx] = data;

  editModal.hide();
}


async function doDelete(){

  const serial = document.getElementById('del_serial').value.trim();
  const invoice = document.getElementById('del_invoice').value.trim();

  if(!serial && !invoice){
    alert("Nhập Serial hoặc Số invoice để xóa");
    return;
  }

  let url = "/api/assets/delete?";
  if(serial){
    url += "serial=" + encodeURIComponent(serial);
  }
  else{
    url += "invoice=" + encodeURIComponent(invoice);
  }

  if(!confirm("Bạn có chắc muốn xóa tài sản?")) return;

  const res = await fetch(url,{
    method:'DELETE'
  });

  const data = await res.json();

  if(!res.ok){
    alert(data.error || "Có lỗi khi xóa");
    return;
  }

  alert(data.message || "Xóa thành công");

  delModal.hide();
  loadTable();

  document.getElementById('del_serial').value = "";
  document.getElementById('del_invoice').value = "";
}

// lookup asset by CLC or Serial for history modal
async function lookupAssetForHist() {
  const v = document.getElementById('hist_lookup').value.trim();
  const el = document.getElementById('hist_found'); 
  el.innerText = '';

  if (!v) {
    el.innerText = 'Nhập Số CLC hoặc Serial để tìm';
    return;
  }

  const res = await fetch('/api/assets');
  const list = await res.json();

  // Tìm theo serial hoặc CLC
  const found = list.find(a => 
      (a.serial && a.serial.toLowerCase() === v.toLowerCase()) ||
      (a.clc && a.clc.toLowerCase() === v.toLowerCase())
  );

  if (!found) {
    el.innerText = 'Không tìm thấy tài sản';
    hist_target_identifier = null;
    return;
  }

  // Quan trọng: chỉ lấy serial
  hist_target_identifier = found.serial;

  el.innerText = `Tìm thấy: Serial=${found.serial}, Tên=${found.name}, CLC=${found.clc || ''}`;
  updateTotalAssets();
}


function onHistTypeChange(){
  const t = document.getElementById('hist_type').value;
  document.getElementById('hist_fault_form').style.display = t === 'fault' ? 'block' : 'none';
  document.getElementById('hist_calib_form').style.display = t === 'calib' ? 'block' : 'none';
}

async function doAddHistory(){
  if(!hist_target_identifier){
    const el = document.getElementById('histAlert'); 
    el.classList.remove('d-none'); 
    el.innerText = 'Bạn phải tìm và chọn tài sản bằng Serial hoặc CLC trước.';
    return;
  }

  const type = document.getElementById('hist_type').value;

  let payload = { 
    serial: hist_target_identifier, 
    type 
  };

  if(type === 'fault'){
    payload.fault = document.getElementById('hist_fault').value.trim();
    payload.fault_date = document.getElementById('hist_fault_date').value;
    payload.sent_date = document.getElementById('hist_sent').value;
    payload.return_date = document.getElementById('hist_return').value || '';
  } 
  else {
    payload.calib_date = document.getElementById('hist_calib_date').value;
    payload.expire_date = document.getElementById('hist_expire_date').value;
  }

  const res = await fetch('/api/assets/history', {
    method:'POST', 
    headers:{'Content-Type':'application/json'}, 
    body: JSON.stringify(payload)
  });

  const data = await res.json();

  if(!res.ok){
    const el = document.getElementById('histAlert'); 
    el.classList.remove('d-none'); 
    
    if(data.missing_fields)
      el.innerText = data.error + ': ' + data.missing_fields.join(', ');
    else 
      el.innerText = data.error || 'Có lỗi';

    return;
  }

  histModal.hide(); 
  loadTable();

  ['hist_lookup','hist_fault','hist_fault_date','hist_sent','hist_return','hist_calib_date','hist_expire_date']
    .forEach(id => document.getElementById(id).value='');

  hist_target_identifier = null;
}

let historyLoading = {};

async function toggleHistory(row, serial){

  if(historyLoading[serial]) return;
  historyLoading[serial] = true;

  let next = row.nextSibling;

  // nếu đang mở → đóng
  if(next && next.classList && next.classList.contains('history-row')){
    next.remove();
    historyLoading[serial] = false;
    return;
  }

  const res = await fetch('/api/assets/history/' + encodeURIComponent(serial));
  const data = await res.json();

  const tr = document.createElement('tr');
  tr.classList.add('history-row');

  const td = document.createElement('td');
  td.colSpan = 12;

  // render history như cũ
  let historyHtml = '';

  if(data.error || data.length === 0){
    historyHtml = '<em>Chưa có lịch sử</em>';
  } else {
    const faults = data.filter(h => h.type === 'fault');
    const calibs = data.filter(h => h.type === 'calib');

    historyHtml += '<h6>Lịch sử lỗi</h6>';

    if(faults.length){
      historyHtml += `<table class="table table-sm">
      <thead><tr><th>Seq</th><th>Tên lỗi</th><th>Ngày lỗi</th><th>Ngày gửi</th><th>Ngày nhận</th></tr></thead><tbody>`;

      for(const h of faults){
        historyHtml += `<tr>
        <td>${h.seq}</td>
        <td>${h.fault || ''}</td>
        <td>${h.fault_date || ''}</td>
        <td>${h.sent_date || ''}</td>
        <td>${h.return_date || ''}</td>
        </tr>`;
      }

      historyHtml += '</tbody></table>';
    } else {
      historyHtml += '<div><em>Không có</em></div>';
    }

    historyHtml += '<h6 class="mt-3">Lịch sử Calib</h6>';

    if(calibs.length){
      historyHtml += `<table class="table table-sm">
      <thead><tr><th>Seq</th><th>Ngày calib</th><th>Ngày hết hạn</th></tr></thead><tbody>`;

      for(const h of calibs){
        historyHtml += `<tr>
        <td>${h.seq}</td>
        <td>${h.calib_date || ''}</td>
        <td>${h.expire_date || ''}</td>
        </tr>`;
      }

      historyHtml += '</tbody></table>';
    } else {
      historyHtml += '<div><em>Không có</em></div>';
    }
  }

  const filesHtml = await renderFiles(serial);

  td.innerHTML = `
  <div class="row">
    <div class="col-md-7">${historyHtml}</div>
    <div class="col-md-5">
      <h6>📎 File đính kèm</h6>
      ${filesHtml}
    </div>
  </div>`;

  tr.appendChild(td);
  row.parentNode.insertBefore(tr, row.nextSibling);

  historyLoading[serial] = false;
}

async function uploadFiles(serial) {
  const input = document.getElementById(`file_input_${serial}`);
  if (!input || input.files.length === 0) {
    alert("Chọn ít nhất 1 file");
    return;
  }

  const fd = new FormData();
  for (const f of input.files) {
    fd.append("files", f);
  }

  const res = await fetch(`/api/assets/${encodeURIComponent(serial)}/files`, {
    method: "POST",
    body: fd
  });

  if (!res.ok) {
    let msg = "Upload file thất bại";
    try {
      const data = await res.json();
      if (data.error) msg = data.error;
    } catch (e) {}

    alert(msg);
    return;
  }


  // Reload lại history + file
  toggleHistory(
    document.querySelector(`tr[data-serial="${serial}"]`),
    serial
  );
}


async function renderFiles(serial) {
  const res = await fetch(`/api/assets/${encodeURIComponent(serial)}/files`);
  const files = await res.json();

  let html = `
    <div class="mb-2">
      <input type="file" id="file_input_${serial}" class="form-control form-control-sm" multiple>
      <button class="btn btn-sm btn-success mt-1"
        onclick="uploadFiles('${serial}')">Thêm file</button>
    </div>
  `;

  if (!files.length) {
    html += "<em>Chưa có file đính kèm</em>";
    return html;
  }

  html += `
    <table class="table table-sm">
      <thead>
        <tr>
          <th>Tên file</th>
          <th>Dung lượng</th>
          <th>Ngày</th>
          <th width="120">Thao tác</th>
        </tr>
      </thead>
      <tbody>
  `;

  for (const f of files) {
    html += `
      <tr>
        <td>${f.file_name}</td>
        <td>${formatFileSize(f.file_size)}</td>
        <td>${(f.created_at || "").substring(0,10)}</td>
        <td>
          <button class="btn btn-sm btn-outline-primary"
            onclick="downloadFile('${f.id}')">Tải</button>
          <button class="btn btn-sm btn-outline-danger ms-1"
            onclick="deleteFile('${f.id}', '${serial}')">Xóa</button>
        </td>
      </tr>
    `;
  }

  html += "</tbody></table>";
  return html;
}


async function downloadFile(id) {
  const res = await fetch(`/api/assets/files/${id}/download`);
  const data = await res.json();
  if (data.url) window.open(data.url, "_blank");
}

async function deleteFile(id, serial) {
  if (!confirm("Bạn có chắc muốn xóa file này?")) return;

  const res = await fetch(`/api/assets/files/${id}`, { method: "DELETE" });
  if (!res.ok) return alert("Xóa file thất bại");

  // reload lại history + file
  toggleHistory(
    document.querySelector(`tr[data-serial="${serial}"]`),
    serial
  );
}


document.addEventListener('DOMContentLoaded', ()=>{
  loadTable();
  initSorting();
});
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
        res = supabase.table("assets").select("*").order("id", desc=False).execute()
        assets = res.data or []

        # Tạo STT (index) động — không lưu trong DB
        out = []
        for i, a in enumerate(assets, start=1):
            item = transform_asset_for_frontend(a)
            item["index"] = i
            out.append(item)

        return jsonify(out), 200
    except Exception as e:
        app.logger.error("api_list_assets error: %s", e)
        return jsonify({"error": str(e)}), 500

# ---- API: add asset ----
@app.route("/api/assets", methods=["POST"])
def api_add_asset():
    data = request.get_json() or {}

    # Bắt buộc phải có serial hoặc invoice
    if not data.get("serial") and not data.get("invoice_no"):
        return jsonify({
            "error": "Phải nhập Serial hoặc Số invoice"
        }), 400

    try:

        # check trùng mã tài sản
        if data.get("code"):
            dup = supabase.table("assets") \
                .select("code") \
                .eq("code", data["code"]) \
                .limit(1) \
                .execute()

            if dup.data:
                return jsonify({"error": "Mã tài sản đã tồn tại"}), 400

        # check trùng serial
        if data.get("serial"):
            dup2 = supabase.table("assets") \
                .select("serial") \
                .eq("serial", data["serial"]) \
                .limit(1) \
                .execute()

            if dup2.data:
                return jsonify({"error": "Serial đã tồn tại"}), 400

        # xử lý date rỗng
        data = normalize_dates(data)

        ins = supabase.table("assets").insert(data).execute()
        created = ins.data[0]

        return jsonify(transform_asset_for_frontend(created)), 201

    except Exception as e:
        app.logger.error("api_add_asset error: %s", e)
        return jsonify({"error": str(e)}), 500

# ---- API: get asset by serial ----
@app.route("/api/assets/<serial>", methods=["GET"])
def api_get_asset(serial):
    try:
        res = supabase.table("assets").select("*").eq("serial", serial).limit(1).execute()
        if not res.data:
            return jsonify({"error": "Không tìm thấy mã serial"}), 404
        asset = transform_asset_for_frontend(res.data[0])
        return jsonify(asset), 200
    except Exception as e:
        app.logger.error("api_get_asset error: %s", e)
        return jsonify({"error": str(e)}), 500

# ---- API UPDATE ASSET ----
@app.route("/api/assets/<int:asset_id>", methods=["PUT", "PATCH"])
def api_update_asset(asset_id):
    try:
        body = request.get_json() or {}
        body = normalize_dates(body)

        existing = supabase.table("assets").select("*").eq("id", asset_id).single().execute()
        if not existing.data:
            return jsonify({"error": "Asset not found"}), 404

        old_asset = existing.data

        allowed_fields = {
            "clc", "code", "name", "brand", "model", "serial",
            "location", "status", "import_date", "warranty_end", "description",
            "declaration_no", "declaration_date", "invoice_no", "invoice_date",
            "supplier",
        }

        update_data = {k: v for k, v in body.items() if k in allowed_fields}

        if not update_data:
            return jsonify({"error": "No valid fields to update"}), 400

        if "code" in update_data:
            new_code = update_data["code"].strip()
            if new_code != (old_asset.get("code") or ""):
                dup_check = supabase.table("assets").select("code").eq("code", new_code).execute()
                if dup_check.data:
                    return jsonify({"error": "Mã tài sản đã tồn tại"}), 400

        res = (
            supabase.table("assets")
            .update(update_data)
            .eq("id", asset_id)
            .execute()
        )

        return jsonify(res.data[0]), 200

    except Exception as e:
        app.logger.error("api_update_asset error: %s", e)
        return jsonify({"error": str(e)}), 500


# ---- API DELETE ----
@app.route("/api/assets/delete", methods=["DELETE"])
def api_delete_asset():

    serial = request.args.get("serial")
    invoice = request.args.get("invoice")

    if not serial and not invoice:
        return jsonify({"error": "Missing serial hoặc invoice"}), 400

    try:

        # ===== XÓA THEO SERIAL =====
        if serial:

            files = supabase.table("asset_files") \
                .select("file_path") \
                .eq("serial", serial) \
                .execute()

            if files.data:
                paths = [f["file_path"] for f in files.data]
                supabase.storage.from_("asset-files").remove(paths)

            supabase.table("asset_files").delete().eq("serial", serial).execute()
            supabase.table("assets").delete().eq("serial", serial).execute()

            return jsonify({"message": "Đã xóa tài sản theo serial"}), 200


        # ===== XÓA THEO INVOICE =====

        assets = supabase.table("assets") \
            .select("serial") \
            .eq("invoice_no", invoice) \
            .execute()

        if not assets.data:
            return jsonify({"error": "Không tìm thấy tài sản với invoice này"}), 404

        serials = [a["serial"] for a in assets.data if a["serial"]]

        # xóa file storage
        if serials:
            files = supabase.table("asset_files") \
                .select("file_path") \
                .in_("serial", serials) \
                .execute()

            if files.data:
                paths = [f["file_path"] for f in files.data]
                supabase.storage.from_("asset-files").remove(paths)

            supabase.table("asset_files").delete().in_("serial", serials).execute()

        # xóa assets
        supabase.table("assets").delete().eq("invoice_no", invoice).execute()

        return jsonify({
            "message": f"Đã xóa {len(assets.data)} tài sản theo invoice"
        }), 200


    except Exception as e:
        app.logger.error("api_delete_asset error: %s", e)
        return jsonify({"error": str(e)}), 500



# ---- API: get history ----
@app.route("/api/assets/history/<serial>", methods=["GET"])
def api_get_history_by_serial(serial):
    try:
        res = supabase.table("asset_history").select("*").eq("serial", serial).order("seq", desc=False).execute()
        return jsonify(res.data or []), 200
    except Exception as e:
        app.logger.error("api_get_history error: %s", e)
        return jsonify({"error": str(e)}), 500

# ---- API add history ----
@app.route("/api/assets/history", methods=["POST"])
def api_add_history():
    body = request.get_json() or {}
    body = normalize_dates(body)

    serial = body.get("serial")
    if not serial:
        return jsonify({"error": "Missing serial"}), 400

    history_type = body.get("type")
    if history_type not in ("fault", "calib"):
        return jsonify({"error": "Missing or invalid type"}), 400

    try:
        res = supabase.table("assets").select("serial").eq("serial", serial).limit(1).execute()
        if not res.data:
            return jsonify({"error": "Asset not found"}), 404

        last = (
            supabase.table("asset_history")
            .select("seq")
            .eq("serial", serial)
            .order("seq", desc=True)
            .limit(1)
            .execute()
        )
        seq = (last.data[0]["seq"] + 1) if last.data else 1

        entry = {
            "serial": serial,
            "type": history_type,
            "seq": seq
        }

        if history_type == "fault":
            entry["fault"] = body.get("fault")
            entry["fault_date"] = body.get("fault_date")
            entry["sent_date"] = body.get("sent_date")
            entry["return_date"] = body.get("return_date")

            missing = [k for k in ("fault", "fault_date") if not entry.get(k)]
            if missing:
                return jsonify({"error": "Thiếu thông tin", "missing_fields": missing}), 400

        else:
            entry["calib_date"] = body.get("calib_date")
            entry["expire_date"] = body.get("expire_date")

            missing = [k for k in ("calib_date", "expire_date") if not entry.get(k)]
            if missing:
                return jsonify({"error": "Thiếu thông tin", "missing_fields": missing}), 400

        ins = supabase.table("asset_history").insert(entry).execute()

        return jsonify(ins.data[0]), 201

    except Exception as e:
        app.logger.error("api_add_history error: %s", e)
        return jsonify({"error": str(e)}), 500


# ---- EXPORT EXCEL ----
@app.route("/export/excel", methods=["GET"])
def export_excel():
    try:
        assets = supabase.table("assets").select("*").order("id", desc=False).execute()
        history = supabase.table("asset_history").select("*").order("seq", desc=False).execute()

        wb = openpyxl.Workbook()
        ws1 = wb.active
        ws1.title = "Assets"

        # ==== Header GIỐNG GIAO DIỆN ====
        headers = [
            "STT", "Số CLC", "Mã tài sản", "Số tờ khai",
            "Ngày tờ khai", "Số invoice", "Ngày hóa đơn",
            "Nhà cung cấp", "Tên máy", "Hãng", "Model",
            "Mô tả", "Serial", "Vị trí", "Trạng thái",
            "Ngày nhập", "Hạn bảo hành", "Hiệu lực bảo hành"
        ]
        ws1.append(headers)

        # ==== Ghi từng dòng ====
        for i, a in enumerate(assets.data or [], start=1):

            # Tính hiệu lực bảo hành (sửa theo yêu cầu)
            statusWarranty = ""

            w_end = a.get("warranty_end")
            if w_end:
                try:
                    d = datetime.strptime(w_end, "%Y-%m-%d").date()
                    if d >= date.today():
                        statusWarranty = "Còn hạn"
                    else:
                        statusWarranty = "Hết hạn"
                except:
                    # Nếu lỗi format ngày → để rỗng luôn
                    statusWarranty = ""
            else:
                # Không có ngày bảo hành → để rỗng
                statusWarranty = ""

            ws1.append([
                i,
                a.get("clc", ""),
                a.get("code", ""),
                a.get("declaration_no", ""),
                a.get("declaration_date", ""),
                a.get("invoice_no", ""),
                a.get("invoice_date", ""),
                a.get("supplier", ""),
                a.get("name", ""),
                a.get("brand", ""),
                a.get("model", ""),
                a.get("description", ""),
                a.get("serial", ""),
                a.get("location", ""),
                a.get("status", ""),
                a.get("import_date", ""),
                a.get("warranty_end", ""),
                statusWarranty
            ])


        # ==== Sheet lịch sử =====
        ws2 = wb.create_sheet("History")
        ws2.append([
            'serial', 'type', 'seq',
            'fault', 'fault_date', 'sent_date', 'return_date',
            'calib_date', 'expire_date'
        ])

        for h in (history.data or []):
            ws2.append([
                h.get("serial", ""),
                h.get("type", ""),
                h.get("seq", ""),
                h.get("fault", ""),
                h.get("fault_date", ""),
                h.get("sent_date", ""),
                h.get("return_date", ""),
                h.get("calib_date", ""),
                h.get("expire_date", "")
            ])

        fp = tempfile.gettempdir() + "/assets_export.xlsx"
        wb.save(fp)
        return send_file(fp, as_attachment=True, download_name="assets.xlsx")

    except Exception as e:
        app.logger.error("export_excel error: %s", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/assets/<serial>/files", methods=["POST"])
def api_upload_asset_files(serial):

    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

    # Kiểm tra có file không
    if "files" not in request.files:
        return jsonify({"error": "Không có file được gửi lên"}), 400

    files = request.files.getlist("files")

    # Kiểm tra asset tồn tại
    chk = (
        supabase.table("assets")
        .select("serial")
        .eq("serial", serial)
        .limit(1)
        .execute()
    )
    if not chk.data:
        return jsonify({"error": "Asset không tồn tại"}), 404

    uploaded = []

    for f in files:
        # 1️⃣ Chuẩn hóa tên file
        filename = secure_filename(f.filename)
        if not filename:
            continue

        # 2️⃣ Đo dung lượng file (AN TOÀN – KHÔNG DÙNG content_length)
        f.stream.seek(0, os.SEEK_END)
        file_size = f.stream.tell()
        f.stream.seek(0)

        if file_size > MAX_FILE_SIZE:
            return jsonify({
                "error": f"File '{filename}' vượt quá dung lượng cho phép (5MB)"
            }), 400

        name, ext = os.path.splitext(filename)

        # 3️⃣ Xử lý TRÙNG TÊN FILE (tự động thêm timestamp)
        path = f"{serial}/{filename}"

        dup = (
            supabase.table("asset_files")
            .select("id")
            .eq("serial", serial)
            .eq("file_name", filename)
            .limit(1)
            .execute()
        )

        if dup.data:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"{name}_{ts}{ext}"
            path = f"{serial}/{filename}"

        # 4️⃣ Upload lên Supabase Storage
        supabase.storage.from_("asset-files").upload(
            path,
            f.read(),
            {"content-type": f.content_type}
        )

        # 5️⃣ Lưu metadata vào DB
        supabase.table("asset_files").insert({
            "serial": serial,
            "file_name": filename,
            "file_path": path,
            "file_size": file_size,
            "content_type": f.content_type
        }).execute()

        uploaded.append({
            "file_name": filename,
            "file_size": file_size
        })

    if not uploaded:
        return jsonify({"error": "Không có file hợp lệ để upload"}), 400

    return jsonify({
        "ok": True,
        "uploaded": uploaded
    }), 201


@app.route("/api/assets/<serial>/files", methods=["GET"])
def api_list_asset_files(serial):
    res = supabase.table("asset_files") \
        .select("id,file_name,file_size,created_at") \
        .eq("serial", serial) \
        .order("created_at", desc=True) \
        .execute()

    return jsonify(res.data or []), 200

@app.route("/api/assets/files/<file_id>/download", methods=["GET"])
def api_download_file(file_id):
    res = supabase.table("asset_files") \
        .select("file_path") \
        .eq("id", file_id) \
        .single() \
        .execute()

    if not res.data:
        return jsonify({"error": "File not found"}), 404

    signed = supabase.storage \
        .from_("asset-files") \
        .create_signed_url(res.data["file_path"], 60)

    return jsonify({"url": signed["signedURL"]}), 200

@app.route("/api/assets/files/<file_id>", methods=["DELETE"])
def api_delete_file(file_id):
    res = supabase.table("asset_files") \
        .select("file_path") \
        .eq("id", file_id) \
        .single() \
        .execute()

    if not res.data:
        return jsonify({"error": "File not found"}), 404

    supabase.storage.from_("asset-files").remove([res.data["file_path"]])
    supabase.table("asset_files").delete().eq("id", file_id).execute()

    return jsonify({"ok": True}), 200

@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    return jsonify({"error": "File vượt quá dung lượng cho phép (5MB)"}), 413

@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Run server at http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port)