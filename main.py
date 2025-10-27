#!/usr/bin/env python3
"""
VPNpower node agent — keep Xray REALITY clients in sync with backend.

Reads environment variables (systemd EnvironmentFile=/etc/vpnpower/agent.env):
  SUB_BASE_URL       # e.g. https://vpnpower.ru
  NODE_SYNC_SECRET   # shared secret for /api/nodes/active-uuids
  XRAY_CONFIG        # default: /usr/local/etc/xray/config.json
  INBOUND_TAG        # default: vless-reality-in

Implementation detail:
- Writes a temporary file in the SAME DIRECTORY as XRAY_CONFIG and then
  atomically replaces the target (avoids EXDEV when PrivateTmp=yes).
"""

import json
import os
import sys
import tempfile
import urllib.request
import subprocess
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name, default)
    if not v:
        print(f"[agent] ERROR: required env {name} is empty", file=sys.stderr)
        sys.exit(2)
    return v


def http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "vpnpower-agent/1"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = r.read()
    return json.loads(data.decode("utf-8"))


def load_config(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception as e:
        print(f"[agent] ERROR: cannot read {path}: {e}", file=sys.stderr)
        sys.exit(3)


def save_atomic(path: Path, data: dict):
    dstdir = path.parent
    # Write temp file in the SAME directory to avoid cross-device rename (EXDEV)
    fd, tmpname = tempfile.mkstemp(prefix=".vpnpower-", suffix=".json", dir=str(dstdir))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmpname, path)  # atomic within the same filesystem
    finally:
        # If something went wrong before replace(), try to cleanup
        try:
            if os.path.exists(tmpname):
                os.unlink(tmpname)
        except Exception:
            pass


def ensure_clients(cfg: dict, inbound_tag: str, uuids: list[str], flow: str) -> bool:
    changed = False
    for inbound in cfg.get("inbounds", []):
        if inbound.get("tag") != inbound_tag:
            continue
        clients = inbound.get("settings", {}).get("clients", [])
        # Build a dict by id for quick access
        by_id = {c.get("id"): c for c in clients}
        # Add/update clients from remote
        for uid in uuids:
            cur = by_id.get(uid)
            if not cur:
                clients.append({"id": uid, "flow": flow})
                changed = True
            else:
                if cur.get("flow") != flow:
                    cur["flow"] = flow
                    changed = True
        # Drop extra clients that are not in remote list
        keep = set(uuids)
        if any(c.get("id") not in keep for c in clients):
            inbound["settings"]["clients"] = [c for c in clients if c.get("id") in keep]
            changed = True
    return changed


def main():
    base = _env("SUB_BASE_URL")
    secret = _env("NODE_SYNC_SECRET")
    xr_path = Path(os.environ.get("XRAY_CONFIG", "/usr/local/etc/xray/config.json"))
    inbound_tag = os.environ.get("INBOUND_TAG", "vless-reality-in")

    url = f"{base.rstrip('/')}/api/nodes/active-uuids?secret={secret}"
    remote = http_get_json(url)
    flow = remote.get("flow") or "xtls-rprx-vision"
    uuids = remote.get("uuids") or []

    if not uuids:
        print("[agent] WARNING: backend returned no uuids; nothing to do")
        return

    cfg = load_config(xr_path)
    if ensure_clients(cfg, inbound_tag, uuids, flow):
        save_atomic(xr_path, cfg)
        print(f"[agent] Updated {xr_path} with {len(uuids)} clients (flow={flow}).")
        # try reload xray
        subprocess.run(["systemctl", "try-reload-or-restart", "xray"], check=False)
    else:
        print("[agent] No changes needed.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[agent] ERROR: {e}", file=sys.stderr)
        sys.exit(1)
