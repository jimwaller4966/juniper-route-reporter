# juniper-route-reporter

Collect `show route table inet.0` from Juniper (Junos) devices via SSH and
render an interactive HTML report with filterable, sortable tables per
device and protocol. Includes a before/after compare tool for diffing two
snapshots — take one, make a change, take another, and see exactly what
moved.

Only `inet.0` (the default unicast IPv4 table) is in scope — no mgmt table,
no inet6, no VRFs/routing-instances.

Same shape as `arista-bgp-reporter`, ported for Junos route tables instead of
Arista BGP detail.

## Requirements

    pip install netmiko

## Usage

### 1. Configure devices

    cp devices.txt.example devices.txt
    # Edit devices.txt - one hostname or IP per line

### 2. Collect

    python3 collect_junos.py
    # Prompts for credentials, saves output/<host>_show_route_table_inet_0.txt

Before touching every device, the collector validates your username/password
against the **first** device in `devices.txt` with a single connection
attempt. If that fails, it re-prompts (up to 3 tries) instead of firing a
typo'd password at every device in parallel — some AAA/RADIUS setups lock an
account out after a handful of failures across multiple devices in a short
window.

### 3. Parse and render

    python3 parse_route.py
    # Generates results/route_report_<timestamp>.html

Open the report in any browser.

### 4. Compare two snapshots (optional)

    open route_compare.html

Run steps 2-3 once to get a "before" report, make your change, run steps 2-3
again for an "after" report, then open `route_compare.html` in a browser and
pick both report files. It's a standalone static page (no server, no
script) — it reads the data embedded in the two report HTML files and shows
you routes added, removed, or changed (next-hop, metric/pref/MED/tag,
AS path, or which one is active).

## Report features

- Live search across all fields
- Filter by Device, Table, Protocol, Prefix, AS Path, Next Hop
- "Active only" toggle (Junos `*` / active-route flag)
- Sortable columns, CSV export
- Stats bar: devices, routing tables, total/active routes, BGP/OSPF counts

## Adding parsers

Same extension pattern as `arista-bgp-reporter`:
1. Create `parsers/<name>.py` with `parse(host, raw)`, `COLUMNS`, `TITLE`, `COMMAND`, `COMMAND_SLUGS`
2. Clone `parse_route.py` to `parse_<name>.py` pointing to the new parser
3. Add the command to `DEFAULT_COMMANDS` in `collect_junos.py` or pass it with `-c`

## Parser details

`parsers/route.py` turns Junos `show route` output into one record per route
entry (one `[protocol/preference]` line), not one per next-hop — a route with
multiple equal-cost next-hops (ECMP) has them joined into a single
`next_hop` field (`10.1.1.1 via irb.10; 10.1.1.2 via irb.20`).

Handles: multipath (several protocol entries per prefix), ECMP, `Discard` /
`MultiRecv` / `Local` special next-hops, and prefixes long enough that Junos
wraps them onto their own line (common with IPv6).
