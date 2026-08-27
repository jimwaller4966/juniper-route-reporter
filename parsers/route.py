"""
parsers/route.py — Parser for Junos 'show route table inet.0' output.

Each record represents one route entry (one [protocol/preference] line) for a
prefix, not one next-hop. If a route has multiple equal-cost next-hops (ECMP),
they're joined into a single next_hop field.

Only inet.0 is in scope for this tool — that's what collect_junos.py requests
and what route_compare.html diffs. The parser itself is table-agnostic (it
just reads whatever table headers appear in the raw text), so pointing it at
output from a different 'show route table <name>' command works too.

Fields per record:
    host, table, prefix, protocol, preference, active,
    age, metric, local_pref, med, tag, as_path, next_hop
"""
import re

TITLE        = "Junos Route Table (inet.0)"
COMMAND      = "show route table inet.0"
COMMAND_SLUGS = [
    "show_route_table_inet_0",
    "show_route",
]

COLUMNS = [
    {"key": "host",       "label": "Device"},
    {"key": "table",      "label": "Table"},
    {"key": "prefix",     "label": "Prefix"},
    {"key": "protocol",   "label": "Protocol"},
    {"key": "preference", "label": "Pref"},
    {"key": "metric",     "label": "Metric"},
    {"key": "local_pref", "label": "Local Pref"},
    {"key": "med",        "label": "MED"},
    {"key": "tag",        "label": "Tag"},
    {"key": "as_path",    "label": "AS Path"},
    {"key": "next_hop",   "label": "Next Hop"},
    {"key": "age",        "label": "Age"},
    {"key": "active",     "label": "Active"},
]

# ── Line patterns ───────────────────────────────────────────────────────────
# Table header, e.g.:
#   inet.0: 37 destinations, 49 routes (37 active, 0 holddown, 3 hidden)
_TABLE_RE = re.compile(
    r"^(?P<table>\S+):\s+\d+\s+destinations,\s+\d+\s+routes\s+\(\d+\s+active"
)

# A route entry line, e.g.:
#   10.1.1.60/32       *[BGP/170] 5d 23:58:04, localpref 100
#                       [OSPF/175] 5d 20:48:59, metric 20, tag 0
#   3fff:172:20:20::/64*[Direct/0] 6d 03:49:23
# The prefix part is optional (may be blank for a continuation path, or
# missing because it wrapped onto its own line above).
_ROUTE_RE = re.compile(
    r"^(?P<prefix>\S*?)\s*(?P<flags>[+\-]?\*)?\[(?P<protocol>[A-Za-z0-9_\-]+)/(?P<pref>\d+)\]"
    r"(?:\s+(?P<rest>.*))?$"
)

# Next-hop line, e.g.:
#   >  to 10.248.10.2 via irb.10
#      to 10.248.10.17 via irb.30      (ECMP, no '>')
_NEXTHOP_TO_RE = re.compile(r"^>?\s*to\s+(?P<nh>\S+)\s+via\s+(?P<iface>\S+)")
# Directly-connected / local, e.g.:
#   >  via lo0.0
_NEXTHOP_VIA_RE = re.compile(r"^>\s*via\s+(?P<iface>\S+)$")
_LOCAL_VIA_RE   = re.compile(r"^Local via\s+(?P<iface>\S+)$")
_AS_PATH_RE     = re.compile(r"^AS path:\s*(?P<as_path>.+?)(?:,\s*validation-state.*)?$")

_ATTR_PATTERNS = {
    "metric":     re.compile(r"\bmetric\s+(\d+)\b"),
    "local_pref": re.compile(r"\blocalpref\s+(\d+)\b"),
    "med":        re.compile(r"\bMED\s+(\d+)\b"),
    "tag":        re.compile(r"\btag\s+(\S+)\b"),
}


def _looks_like_new_section(line):
    """A blank line or a new table header ends the current record's continuation lines."""
    return not line.strip() or _TABLE_RE.match(line)


def parse(host, raw_text):
    """
    Parse raw 'show route' output. Returns list of dicts, one per route entry.
    """
    records = []
    lines = raw_text.splitlines()

    table = "—"
    pending_prefix = None   # set when a prefix appears alone on its own line
    current_prefix = None   # last real prefix seen — continuation paths reuse it
    current = None          # in-progress record dict, flushed when a new one starts

    def flush():
        nonlocal current
        if current is not None:
            if not current["next_hop"]:
                current["next_hop"] = "—"
            else:
                current["next_hop"] = "; ".join(current["next_hop"])
            records.append(current)
        current = None

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        i += 1

        # New table section
        m = _TABLE_RE.match(line)
        if m:
            flush()
            table = m.group("table")
            pending_prefix = None
            current_prefix = None
            continue

        if not line.strip():
            continue

        # Skip legend / limit lines
        if line.startswith("+ = Active Route") or line.startswith("Limit/Threshold"):
            continue

        m = _ROUTE_RE.match(line)
        if m:
            flush()
            prefix = m.group("prefix") or pending_prefix or current_prefix or "—"
            pending_prefix = None
            current_prefix = prefix
            rest = m.group("rest") or ""
            age = rest.split(",")[0].strip() if rest else "—"

            current = {
                "host":        host,
                "table":       table,
                "prefix":      prefix,
                "protocol":    m.group("protocol"),
                "preference":  m.group("pref"),
                "active":      "✓" if m.group("flags") else "",
                "age":         age or "—",
                "metric":      "—",
                "local_pref":  "—",
                "med":         "—",
                "tag":         "—",
                "as_path":     "—",
                "next_hop":    [],
            }
            for key, pat in _ATTR_PATTERNS.items():
                am = pat.search(rest)
                if am:
                    current[key] = am.group(1)
            continue

        # Continuation lines for the in-progress record
        stripped = line.strip()

        m = _AS_PATH_RE.match(stripped)
        if m and current is not None:
            current["as_path"] = m.group("as_path").strip()
            continue

        m = _NEXTHOP_TO_RE.match(stripped)
        if m and current is not None:
            current["next_hop"].append(f"{m.group('nh')} via {m.group('iface')}")
            continue

        m = _NEXTHOP_VIA_RE.match(stripped)
        if m and current is not None:
            current["next_hop"].append(f"via {m.group('iface')}")
            continue

        m = _LOCAL_VIA_RE.match(stripped)
        if m and current is not None:
            current["next_hop"].append(f"local via {m.group('iface')}")
            continue

        if stripped == "Discard" and current is not None:
            current["next_hop"].append("Discard")
            continue

        if stripped == "MultiRecv" and current is not None:
            current["next_hop"].append("MultiRecv")
            continue

        # Not a bracket line, not a recognized continuation — likely a prefix
        # that wrapped onto its own line because it was too long to fit
        # before the '[proto/pref]' column. Buffer it for the next line.
        flush()
        pending_prefix = stripped

    flush()
    return records
