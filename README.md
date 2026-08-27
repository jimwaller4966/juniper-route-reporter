# juniper-route-reporter

Collect `show route` from Juniper (Junos) devices via SSH and render an
interactive HTML report with filterable, sortable tables per device, routing
table, and protocol.

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
    # Prompts for credentials, saves output/<host>_show_route_all.txt

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

## Report features

- Live search across all fields
- Filter by Device, Table, Protocol, Prefix, AS Path, Next Hop
- "Active only" toggle (Junos `*` / active-route flag)
- Sortable columns, CSV export
- Stats bar: devices, routing tables, total/active routes, BGP/OSPF counts

## Routing-instance note

Default command is `show route all`, which includes every routing-instance on
the device, not just the default one (`inet.0`). If a device doesn't support
`all`, re-run with:

    python3 collect_junos.py "show route"

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
