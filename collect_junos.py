#!/usr/bin/env python3
"""
collect_junos.py — SSH into a list of Juniper (Junos) devices and collect CLI output.

Usage:
    python3 collect_junos.py                            # runs default command list
    python3 collect_junos.py "show route table inet.0"   # run a single command
    python3 collect_junos.py -c commands.txt             # run commands from a file

Device list: devices.txt (one hostname/IP per line, # for comments)
Output:      output/<hostname>_<sanitized_command>.txt

Credential validation:
    Before fanning out to every device in parallel, this script validates the
    username/password against the FIRST device in devices.txt with a single
    connection attempt. If that fails (bad password, etc.), it re-prompts
    instead of hammering every device with a typo'd password — some AAA/RADIUS
    setups lock an account out after a handful of failures across multiple
    devices in a short window.

Scope:
    Default command is 'show route table inet.0' — only the default unicast
    IPv4 table. That's the table this tool (and route_compare.html) cares
    about; mgmt_junos.inet.0, inet6.0, and VRF/routing-instance tables are
    intentionally left out. To collect a different table, pass it explicitly:
        python3 collect_junos.py "show route table <name>"
"""

import argparse
import getpass
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
except ImportError:
    print("ERROR: netmiko not installed. Run: pip install netmiko")
    sys.exit(1)

OUTPUT_DIR = "output"

DEFAULT_COMMANDS = [
    "show route table inet.0",
]

MAX_AUTH_ATTEMPTS = 3


def load_devices(path="devices.txt"):
    if not os.path.exists(path):
        print(f"ERROR: Device list '{path}' not found.")
        print("Create devices.txt with one hostname or IP per line.")
        sys.exit(1)
    devices = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                devices.append(line)
    if not devices:
        print("ERROR: No devices found in devices.txt")
        sys.exit(1)
    return devices


def sanitize(cmd):
    """Convert a command string to a safe filename component."""
    return re.sub(r"[^a-z0-9]+", "_", cmd.lower()).strip("_")


def validate_credentials(host, username, password, timeout):
    """
    Try a single lightweight connection to `host`. Returns (True, None) on
    success, (False, reason) on auth failure. Other errors (host unreachable,
    timeout) are NOT treated as auth failures — those don't indicate a bad
    password, so they're reported but don't block the run.
    """
    try:
        conn = ConnectHandler(
            device_type="juniper_junos",
            host=host,
            username=username,
            password=password,
            timeout=timeout,
            session_log=None,
        )
        conn.disconnect()
        return True, None
    except NetmikoAuthenticationException:
        return False, "Authentication failed"
    except NetmikoTimeoutException:
        print(f"  [WARN] {host}: connection timed out during credential check "
              f"(not an auth failure — continuing)")
        return True, None
    except Exception as e:
        print(f"  [WARN] {host}: {e} (not an auth failure — continuing)")
        return True, None


def collect_device(host, username, password, commands, timeout=30):
    """Connect to a single device and run all commands. Returns (host, results, error)."""
    results = {}
    try:
        conn = ConnectHandler(
            device_type="juniper_junos",
            host=host,
            username=username,
            password=password,
            timeout=timeout,
            session_log=None,
        )
        for cmd in commands:
            output = conn.send_command(cmd, read_timeout=90)
            if output.strip().startswith("%") or "unknown command" in output.lower():
                results[cmd] = output
                results[f"__error__{cmd}"] = output.strip()
            else:
                results[cmd] = output
        conn.disconnect()
        return host, results, None
    except NetmikoAuthenticationException:
        return host, {}, "Authentication failed"
    except NetmikoTimeoutException:
        return host, {}, "Connection timed out"
    except Exception as e:
        return host, {}, str(e)


def save_output(host, cmd, output, timestamp):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"{host}_{sanitize(cmd)}.txt"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w") as f:
        f.write(f"# Host:      {host}\n")
        f.write(f"# Command:   {cmd}\n")
        f.write(f"# Collected: {timestamp}\n")
        f.write("#" + "-" * 60 + "\n\n")
        f.write(output)
    return filepath


def main():
    parser = argparse.ArgumentParser(description="Collect CLI output from Juniper (Junos) devices")
    parser.add_argument("command", nargs="?", help="Single command to run")
    parser.add_argument("-c", "--commands-file", help="File with one command per line")
    parser.add_argument("-d", "--devices", default="devices.txt", help="Device list file")
    parser.add_argument("-w", "--workers", type=int, default=10, help="Parallel SSH workers")
    parser.add_argument("-t", "--timeout", type=int, default=30, help="SSH timeout seconds")
    args = parser.parse_args()

    if args.command:
        commands = [args.command]
    elif args.commands_file:
        with open(args.commands_file) as f:
            commands = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    else:
        commands = DEFAULT_COMMANDS

    devices = load_devices(args.devices)

    print(f"\nJuniper (Junos) CLI Collector")
    print(f"{'='*40}")
    print(f"Devices:  {len(devices)}")
    print(f"Commands: {commands}")
    print(f"Output:   {OUTPUT_DIR}/\n")
    print("NOTE: Default uses 'show route table inet.0'.")
    print("      If a device errors, re-run with a different table, e.g.:")
    print("      python3 collect_junos.py 'show route table <name>'\n")

    username = input("Username: ").strip()

    validation_host = devices[0]
    for attempt in range(1, MAX_AUTH_ATTEMPTS + 1):
        password = getpass.getpass("Password: ")
        print(f"\nValidating credentials against {validation_host} ({attempt}/{MAX_AUTH_ATTEMPTS})...")
        ok, reason = validate_credentials(validation_host, username, password, args.timeout)
        if ok:
            print("  [OK] Credentials accepted.\n")
            break
        print(f"  [FAIL] {reason}")
        if attempt == MAX_AUTH_ATTEMPTS:
            print(f"\nERROR: Authentication failed {MAX_AUTH_ATTEMPTS} times against "
                  f"{validation_host}. Stopping before touching the other "
                  f"{len(devices) - 1} device(s) to avoid an AAA lockout.")
            sys.exit(1)
        print("Re-enter credentials.\n")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    success = 0
    failure = 0
    cmd_errors = []

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(collect_device, host, username, password, commands, args.timeout): host
            for host in devices
        }
        for future in as_completed(futures):
            host, results, error = future.result()
            if error:
                print(f"  [FAIL] {host}: {error}")
                failure += 1
            else:
                for cmd, output in results.items():
                    if cmd.startswith("__error__"):
                        orig_cmd = cmd.replace("__error__", "")
                        cmd_errors.append((host, orig_cmd, output))
                        continue
                    path = save_output(host, cmd, output, timestamp)
                    print(f"  [OK]   {host} -> {path}")
                success += 1

    print(f"\nDone. {success} succeeded, {failure} failed.")

    if cmd_errors:
        print(f"\n{'='*40}")
        print("WARNING: These devices returned errors:")
        for host, cmd, err in cmd_errors:
            print(f"  {host}: {err[:100]}")

    print(f"\nNext step: python3 parse_route.py")


if __name__ == "__main__":
    main()
