#!/usr/bin/env python3
"""
parse_route.py — Parse Junos 'show route' output and render an HTML report.
Usage:
    python3 parse_route.py                  # scans output/ for route files
    python3 parse_route.py -i output/       # explicit input directory
    python3 parse_route.py -o report.html   # custom output filename
"""
import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from parsers import route as PARSER
except ImportError:
    print("ERROR: Cannot find parsers/route.py")
    sys.exit(1)

OUTPUT_DIR  = "output"
RESULTS_DIR = "results"

# ── File loading ──────────────────────────────────────────────────────────────
def load_files(input_dir):
    records = []
    p = Path(input_dir)
    if not p.exists():
        print(f"ERROR: Input directory '{input_dir}' not found.")
        sys.exit(1)
    found = []
    for slug in PARSER.COMMAND_SLUGS:
        found.extend(sorted(p.glob(f"*_{slug}.txt")))
    if not found:
        slugs = ", ".join(f"*_{s}.txt" for s in PARSER.COMMAND_SLUGS)
        print(f"No matching files found in {input_dir}/")
        print(f"Expected filenames matching: {slugs}")
        sys.exit(1)
    for f in found:
        host = f.name.split("_")[0]
        raw  = f.read_text(encoding="utf-8", errors="replace")
        recs = PARSER.parse(host, raw)
        tables = sorted(set(r["table"] for r in recs))
        print(f"  Parsed {host}: {len(recs)} routes across tables: {tables}")
        records.extend(recs)
    return records

# ── HTML report ───────────────────────────────────────────────────────────────
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Junos Route Table Report</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700;800&display=swap');

  :root {
    --bg:        #0a0e14;
    --bg2:       #0f1520;
    --bg3:       #141c2e;
    --border:    #1e2d4a;
    --accent:    #00d4ff;
    --accent2:   #7c3aed;
    --accent3:   #10b981;
    --warn:      #f59e0b;
    --danger:    #ef4444;
    --text:      #e2e8f0;
    --muted:     #64748b;
    --tag-bg:    #1a2640;
    --tag-text:  #7dd3fc;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    min-height: 100vh;
  }

  header {
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    padding: 20px 28px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    flex-wrap: wrap;
  }

  .header-left h1 {
    font-family: 'JetBrains Mono', monospace;
    font-size: 22px;
    font-weight: 800;
    color: var(--accent);
    letter-spacing: -0.5px;
  }

  .header-left .cmd-badge {
    display: inline-block;
    margin-top: 4px;
    background: var(--bg3);
    border: 1px solid var(--border);
    color: var(--muted);
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 4px;
  }

  .header-right {
    color: var(--muted);
    font-size: 11px;
    text-align: right;
  }

  .stats {
    display: flex;
    gap: 0;
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    padding: 0 28px;
    flex-wrap: wrap;
  }

  .stat {
    padding: 14px 24px 14px 0;
    margin-right: 24px;
    border-right: 1px solid var(--border);
  }
  .stat:last-child { border-right: none; }

  .stat-val {
    font-family: 'JetBrains Mono', monospace;
    font-size: 26px;
    font-weight: 800;
    line-height: 1;
    color: var(--accent);
  }
  .stat-val.green  { color: var(--accent3); }
  .stat-val.purple { color: var(--accent2); }
  .stat-val.amber  { color: var(--warn); }

  .stat-label {
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 4px;
  }

  .filters {
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    padding: 12px 28px;
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    align-items: center;
  }

  .filters input, .filters select {
    background: var(--bg3);
    border: 1px solid var(--border);
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    padding: 6px 10px;
    border-radius: 4px;
    outline: none;
    transition: border-color 0.15s;
  }
  .filters input:focus, .filters select:focus { border-color: var(--accent); }
  .filters input::placeholder { color: var(--muted); }

  .filter-label { color: var(--muted); font-size: 11px; white-space: nowrap; }

  .btn-reset {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    padding: 6px 12px;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.15s;
  }
  .btn-reset:hover { border-color: var(--accent); color: var(--accent); }

  .btn-not {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    font-weight: 700;
    padding: 3px 6px;
    border-radius: 3px;
    cursor: pointer;
    transition: all 0.15s;
    letter-spacing: 0.5px;
    line-height: 1;
  }
  .btn-not:hover { border-color: var(--danger); color: var(--danger); }
  .btn-not.active { background: rgba(239,68,68,0.15); border-color: var(--danger); color: var(--danger); }

  .filter-group { display: flex; align-items: center; gap: 4px; }

  .btn-export {
    background: transparent;
    border: 1px solid var(--accent3);
    color: var(--accent3);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    padding: 6px 12px;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .btn-export:hover { background: rgba(16,185,129,0.1); }

  .row-count { margin-left: auto; color: var(--muted); font-size: 11px; white-space: nowrap; }

  .table-wrap { overflow-x: auto; padding: 0 28px 28px; }

  table { width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 12px; }

  thead th {
    background: var(--bg3);
    color: var(--muted);
    font-size: 10px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 8px 10px;
    text-align: left;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
    cursor: pointer;
    user-select: none;
  }
  thead th:hover { color: var(--accent); }
  thead th.sorted { color: var(--accent); }

  tbody tr { border-bottom: 1px solid var(--border); transition: background 0.1s; }
  tbody tr:hover { background: var(--bg3); }
  tbody tr.active-route { background: rgba(16,185,129,0.04); }
  tbody tr.active-route:hover { background: rgba(16,185,129,0.09); }

  td { padding: 7px 10px; color: var(--text); white-space: nowrap; vertical-align: middle; }

  td.prefix  { color: var(--accent); font-weight: 500; }
  td.as-path { color: #94a3b8; }
  td.nexthop { color: #cbd5e1; }

  .badge-table {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.5px;
  }
  .tbl-inet0 { background: #1e3a5f; color: #7dd3fc; }
  .tbl-mgmt  { background: #1a3a2a; color: #6ee7b7; }
  .tbl-other { background: #2a2a1a; color: #fde68a; }

  .badge-proto {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.5px;
  }
  .proto-BGP    { background: #2d1b4e; color: #c4b5fd; }
  .proto-OSPF   { background: #1e3a5f; color: #7dd3fc; }
  .proto-Direct { background: #1a3a2a; color: #6ee7b7; }
  .proto-Local  { background: #1a3a2a; color: #6ee7b7; }
  .proto-Static { background: #2a2a1a; color: #fde68a; }
  .proto-other  { background: #2a2a1a; color: #fde68a; }

  .check { color: var(--accent3); font-weight: 700; }

  .hidden { display: none !important; }
</style>
</head>
<body>

<header>
  <div class="header-left">
    <h1>Junos Route Table</h1>
    <span class="cmd-badge">show route</span>
  </div>
  <div class="header-right">
    Generated __GENERATED__<br>
    __DEVICE_COUNT__ devices &nbsp;·&nbsp; __TABLE_COUNT__ tables
  </div>
</header>

<div class="stats">
  <div class="stat">
    <div class="stat-val">__TOTAL_ROUTES__</div>
    <div class="stat-label">Total Routes</div>
  </div>
  <div class="stat">
    <div class="stat-val green">__TOTAL_PREFIXES__</div>
    <div class="stat-label">Unique Prefixes</div>
  </div>
  <div class="stat">
    <div class="stat-val purple">__ACTIVE_ROUTES__</div>
    <div class="stat-label">Active Routes</div>
  </div>
  <div class="stat">
    <div class="stat-val amber">__BGP_COUNT__</div>
    <div class="stat-label">BGP</div>
  </div>
  <div class="stat">
    <div class="stat-val">__OSPF_COUNT__</div>
    <div class="stat-label">OSPF</div>
  </div>
</div>

<div class="filters">
  <span class="filter-label">Device</span>
  <div class="filter-group">
    <select id="f-device"><option value="">All</option></select>
    <button class="btn-not" id="not-device" onclick="toggleNot('device')" title="Invert filter">NOT</button>
  </div>

  <span class="filter-label">Table</span>
  <div class="filter-group">
    <select id="f-table"><option value="">All</option></select>
    <button class="btn-not" id="not-table" onclick="toggleNot('table')" title="Invert filter">NOT</button>
  </div>

  <span class="filter-label">Protocol</span>
  <div class="filter-group">
    <select id="f-protocol"><option value="">All</option></select>
    <button class="btn-not" id="not-protocol" onclick="toggleNot('protocol')" title="Invert filter">NOT</button>
  </div>

  <span class="filter-label">Prefix</span>
  <div class="filter-group">
    <input id="f-prefix" type="text" placeholder="e.g. 10.10" style="width:130px">
    <button class="btn-not" id="not-prefix" onclick="toggleNot('prefix')" title="Invert filter">NOT</button>
  </div>

  <span class="filter-label">AS Path</span>
  <div class="filter-group">
    <input id="f-aspath" type="text" placeholder="e.g. 64611" style="width:110px">
    <button class="btn-not" id="not-aspath" onclick="toggleNot('aspath')" title="Invert filter">NOT</button>
  </div>

  <span class="filter-label">Next Hop</span>
  <div class="filter-group">
    <input id="f-nexthop" type="text" placeholder="e.g. irb.10" style="width:110px">
    <button class="btn-not" id="not-nexthop" onclick="toggleNot('nexthop')" title="Invert filter">NOT</button>
  </div>

  <div class="filter-group">
    <label style="color:var(--muted);font-size:11px;display:flex;align-items:center;gap:5px;">
      <input type="checkbox" id="f-active"> Active only
    </label>
    <button class="btn-not" id="not-active" onclick="toggleNot('active')" title="Invert filter">NOT</button>
  </div>

  <button class="btn-reset" onclick="resetFilters()">Reset</button>
  <button class="btn-export" onclick="exportCSV()">Export CSV</button>
  <span class="row-count" id="row-count"></span>
</div>

<div class="table-wrap">
  <table id="main-table">
    <thead>
      <tr>
        <th onclick="sortTable(0)">Device</th>
        <th onclick="sortTable(1)">Table</th>
        <th onclick="sortTable(2)">Prefix</th>
        <th onclick="sortTable(3)">Protocol</th>
        <th onclick="sortTable(4)">Pref</th>
        <th onclick="sortTable(5)">Metric</th>
        <th onclick="sortTable(6)">Local Pref</th>
        <th onclick="sortTable(7)">MED</th>
        <th onclick="sortTable(8)">Tag</th>
        <th onclick="sortTable(9)">AS Path</th>
        <th onclick="sortTable(10)">Next Hop</th>
        <th onclick="sortTable(11)">Age</th>
        <th onclick="sortTable(12)">Active</th>
      </tr>
    </thead>
    <tbody id="table-body">
    </tbody>
  </table>
</div>

<script>
const RAW = __JSON_DATA__;

function tableClass(t) {
  if (t === 'inet.0') return 'tbl-inet0';
  if (t.startsWith('mgmt_junos')) return 'tbl-mgmt';
  return 'tbl-other';
}
function protoClass(p) {
  return 'proto-' + (['BGP','OSPF','Direct','Local','Static'].includes(p) ? p : 'other');
}

function buildOptions(id, values) {
  const sel = document.getElementById(id);
  const cur = sel.value;
  while (sel.options.length > 1) sel.remove(1);
  values.forEach(v => {
    const o = document.createElement('option');
    o.value = o.textContent = v;
    sel.appendChild(o);
  });
  sel.value = cur;
}

const notState = {device:false, table:false, protocol:false, prefix:false, aspath:false, nexthop:false, active:false};

function toggleNot(key) {
  notState[key] = !notState[key];
  const btn = document.getElementById('not-' + key);
  btn.classList.toggle('active', notState[key]);
  applyFilters();
}

function applyFilters() {
  const fDevice   = document.getElementById('f-device').value;
  const fTable    = document.getElementById('f-table').value;
  const fProtocol = document.getElementById('f-protocol').value;
  const fPrefix   = document.getElementById('f-prefix').value.trim().toLowerCase();
  const fAspath   = document.getElementById('f-aspath').value.trim().toLowerCase();
  const fNexthop  = document.getElementById('f-nexthop').value.trim().toLowerCase();
  const fActive   = document.getElementById('f-active').checked;

  const rows = document.querySelectorAll('#table-body tr');
  let visible = 0;

  rows.forEach(row => {
    const d = row.dataset;
    let show = true;

    if (fDevice)   { const m = d.device === fDevice;              if (notState.device   ? m : !m) show = false; }
    if (fTable)    { const m = d.table === fTable;                if (notState.table    ? m : !m) show = false; }
    if (fProtocol) { const m = d.protocol === fProtocol;          if (notState.protocol ? m : !m) show = false; }
    if (fPrefix)   { const m = d.prefix.includes(fPrefix);        if (notState.prefix   ? m : !m) show = false; }
    if (fAspath)   { const m = d.aspath.toLowerCase().includes(fAspath);   if (notState.aspath  ? m : !m) show = false; }
    if (fNexthop)  { const m = d.nexthop.toLowerCase().includes(fNexthop); if (notState.nexthop ? m : !m) show = false; }
    if (fActive)   { const m = d.active === '1';                  if (notState.active   ? m : !m) show = false; }

    row.classList.toggle('hidden', !show);
    if (show) visible++;
  });

  document.getElementById('row-count').textContent = `Showing ${visible} of ${rows.length} routes`;
}

function resetFilters() {
  ['f-device','f-table','f-protocol'].forEach(id => document.getElementById(id).value = '');
  ['f-prefix','f-aspath','f-nexthop'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('f-active').checked = false;
  Object.keys(notState).forEach(k => {
    notState[k] = false;
    const btn = document.getElementById('not-' + k);
    if (btn) btn.classList.remove('active');
  });
  applyFilters();
}

function exportCSV() {
  const rows = document.querySelectorAll('#table-body tr:not(.hidden)');
  const headers = ['Device','Table','Prefix','Protocol','Pref','Metric','Local Pref','MED','Tag','AS Path','Next Hop','Age','Active'];

  const csvRows = [headers.join(',')];
  rows.forEach(row => {
    const cells = row.querySelectorAll('td');
    const vals = Array.from(cells).map(c => c.textContent.trim());
    csvRows.push(vals.map(v => '"' + v.replace(/"/g, '""') + '"').join(','));
  });

  const blob = new Blob([csvRows.join('\\n')], {type: 'text/csv'});
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = 'route_report_filtered.csv';
  a.click();
  URL.revokeObjectURL(url);
}

let sortCol = -1, sortAsc = true;
function sortTable(col) {
  if (sortCol === col) sortAsc = !sortAsc; else { sortCol = col; sortAsc = true; }
  document.querySelectorAll('thead th').forEach((th,i) => th.classList.toggle('sorted', i===col));
  const tbody = document.getElementById('table-body');
  const rows  = Array.from(tbody.querySelectorAll('tr'));
  rows.sort((a,b) => {
    const av = a.cells[col]?.textContent.trim() || '';
    const bv = b.cells[col]?.textContent.trim() || '';
    return sortAsc ? av.localeCompare(bv, undefined, {numeric:true}) : bv.localeCompare(av, undefined, {numeric:true});
  });
  rows.forEach(r => tbody.appendChild(r));
}

(function() {
  const devices   = [...new Set(RAW.map(r => r.host))].sort();
  const tables    = [...new Set(RAW.map(r => r.table))].sort();
  const protocols = [...new Set(RAW.map(r => r.protocol))].sort();
  buildOptions('f-device',   devices);
  buildOptions('f-table',    tables);
  buildOptions('f-protocol', protocols);

  const tbody = document.getElementById('table-body');
  const frag = document.createDocumentFragment();
  RAW.forEach(r => {
    const tr = document.createElement('tr');
    if (r.active === '✓') tr.classList.add('active-route');
    tr.dataset.device   = r.host;
    tr.dataset.table    = r.table;
    tr.dataset.protocol = r.protocol;
    tr.dataset.prefix   = r.prefix.toLowerCase();
    tr.dataset.aspath   = r.as_path;
    tr.dataset.nexthop  = r.next_hop;
    tr.dataset.active   = r.active === '✓' ? '1' : '';

    tr.innerHTML = `
      <td>${r.host}</td>
      <td><span class="badge-table ${tableClass(r.table)}">${r.table}</span></td>
      <td class="prefix">${r.prefix}</td>
      <td><span class="badge-proto ${protoClass(r.protocol)}">${r.protocol}</span></td>
      <td style="color:var(--muted)">${r.preference}</td>
      <td>${r.metric}</td>
      <td>${r.local_pref}</td>
      <td>${r.med}</td>
      <td>${r.tag}</td>
      <td class="as-path">${r.as_path}</td>
      <td class="nexthop">${r.next_hop}</td>
      <td style="color:var(--muted)">${r.age}</td>
      <td><span class="check">${r.active}</span></td>
    `;
    frag.appendChild(tr);
  });
  tbody.appendChild(frag);

  ['f-device','f-table','f-protocol'].forEach(id => document.getElementById(id).addEventListener('change', applyFilters));
  ['f-prefix','f-aspath','f-nexthop'].forEach(id => document.getElementById(id).addEventListener('input', applyFilters));
  document.getElementById('f-active').addEventListener('change', applyFilters);

  requestAnimationFrame(applyFilters);
})();
</script>
</body>
</html>
"""

def render_html(records, output_file):
    total_routes    = len(records)
    total_prefixes  = len(set((r["host"], r["table"], r["prefix"]) for r in records))
    active_routes   = sum(1 for r in records if r.get("active") == "✓")
    proto_counts    = Counter(r["protocol"] for r in records)
    device_count    = len(set(r["host"] for r in records))
    table_count     = len(set(r["table"] for r in records))
    generated       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = HTML_TEMPLATE
    html = html.replace("__GENERATED__",       generated)
    html = html.replace("__DEVICE_COUNT__",    str(device_count))
    html = html.replace("__TABLE_COUNT__",     str(table_count))
    html = html.replace("__TOTAL_ROUTES__",    str(total_routes))
    html = html.replace("__TOTAL_PREFIXES__",  str(total_prefixes))
    html = html.replace("__ACTIVE_ROUTES__",   str(active_routes))
    html = html.replace("__BGP_COUNT__",       str(proto_counts.get("BGP", 0)))
    html = html.replace("__OSPF_COUNT__",      str(proto_counts.get("OSPF", 0)))
    html = html.replace("__JSON_DATA__",       json.dumps(records, ensure_ascii=False))

    Path(output_file).write_text(html, encoding="utf-8")
    print(f"Report: {output_file}")
    print(f"Routes: {total_routes} ({active_routes} active) across {table_count} table(s)")
    print(f"By protocol: {dict(proto_counts)}")


def main():
    parser = argparse.ArgumentParser(description="Junos Route Table Report Generator")
    parser.add_argument("-i", "--input",  default=OUTPUT_DIR, help="Input directory")
    parser.add_argument("-o", "--output", default=None,        help="Output HTML file (default: results/route_report_YYYYMMDD_HHMMSS.html)")
    args = parser.parse_args()

    if args.output:
        output_file = args.output
    else:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(RESULTS_DIR, f"route_report_{ts}.html")

    print(f"\nJunos Route Parser")
    print("=" * 40)
    print(f"Input:  {args.input}/")
    print(f"Output: {output_file}")
    print()

    records = load_files(args.input)
    if not records:
        print("No route records parsed.")
        sys.exit(1)

    render_html(records, output_file)


if __name__ == "__main__":
    main()
