# backend/utils_vless.py
# -*- coding: utf-8 -*-

import re
import urllib.parse

UUID_RE = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')


def _pct(s: str) -> str:
    return urllib.parse.quote(s or "", safe="")


def _qs(d: dict) -> str:
    ordered = [
        ("flow", d.get("flow", "xtls-rprx-vision")),
        ("encryption", "none"),
        ("security", "reality"),
        ("sni", d["sni"]),
        ("fp", d.get("fp", "chrome")),
        ("pbk", d["pbk"]),
        ("sid", d["sid"]),
        ("spx", d.get("spx", "/")),
        ("type", d.get("type", "tcp")),
    ]
    return urllib.parse.urlencode(ordered, safe="/:")


def build_vless_uri(
    *,
    uuid: str,
    host: str,
    port: int | str = 443,
    sni: str,
    pbk: str,
    sid: str,
    label: str,
    flow: str = "xtls-rprx-vision",
    fp: str = "chrome",
    spx: str = "/",
    network_type: str = "tcp",
) -> str:
    if not uuid or not UUID_RE.match(uuid):
        raise ValueError("bad uuid")
    if not host or not sni or not pbk or not sid:
        raise ValueError("missing required REALITY fields")

    qs = _qs(
        {"flow": flow, "sni": sni, "fp": fp, "pbk": pbk, "sid": sid, "spx": spx, "type": network_type}
    )
    return f"vless://{uuid}@{host}:{int(port)}?{qs}#{_pct(label)}"
