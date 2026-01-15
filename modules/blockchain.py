"""
Blockchain Tools - Etherscan API integration for tracking thieves.

This module provides tools for:
1. Address monitoring and transaction tracking
2. Token transfer analysis
3. Exchange deposit detection (critical for cashout tracking)
4. Fund tracing

Critical for the $4.2M theft investigation.
Requires ETHERSCAN_API_KEY in .env
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict
import urllib.request
import urllib.parse

def now_iso():
    return datetime.now(timezone.utc).isoformat()

ETHERSCAN_BASE = "https://api.etherscan.io/api"

# Known exchange deposit addresses
KNOWN_EXCHANGES = {
    # Binance
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance Hot Wallet",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance",
    "0x56eddb7aa87536c09ccc2793473599fd21a8b17f": "Binance 17",
    # Coinbase
    "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase",
    "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43": "Coinbase Commerce",
    "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase 2",
    # Kraken
    "0x267be1c1d684f78cb4f6a176c4911b741e4ffdc0": "Kraken",
    "0x2910543af39aba0cd09dbb2d50200b3e800a63d2": "Kraken 2",
    # OKX
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": "OKX",
    "0x98ec059dc3adfbdd63429454aeb0c990fba4a128": "OKX 2",
    # Huobi/HTX
    "0xab5c66752a9e8167967685f1450532fb96d5d24f": "Huobi",
    "0x6748f50f686bfbca6fe8ad62b22228b87f31ff2b": "Huobi 2",
    # Bybit
    "0xf89d7b9c864f589bbf53a82105107622b35eaa40": "Bybit",
    # Gate.io
    "0x0d0707963952f2fba59dd06f2b425ace40b492fe": "Gate.io",
}

KNOWN_MIXERS = {
    "0x722122df12d4e14e13ac3b6895a86e84145b6967": "Tornado Cash",
    "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b": "Tornado Cash Router",
}


class EtherscanClient:
    """Etherscan API client with rate limiting."""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("ETHERSCAN_API_KEY")
        if not self.api_key:
            raise ValueError("ETHERSCAN_API_KEY required")
        self.last_call = 0
        self.rate_delay = 0.21  # 5/sec limit
    
    def _call(self, params: dict) -> dict:
        """Make rate-limited API call."""
        elapsed = time.time() - self.last_call
        if elapsed < self.rate_delay:
            time.sleep(self.rate_delay - elapsed)
        params["apikey"] = self.api_key
        url = f"{ETHERSCAN_BASE}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                self.last_call = time.time()
                return data
        except Exception as e:
            return {"status": "0", "message": str(e), "result": []}
    
    def get_balance(self, address: str) -> dict:
        """Get ETH balance."""
        r = self._call({"module": "account", "action": "balance", "address": address, "tag": "latest"})
        if r.get("status") == "1":
            wei = int(r.get("result", 0))
            return {"address": address, "wei": wei, "eth": wei / 1e18}
        return {"address": address, "eth": 0, "error": r.get("message")}
    
    def get_transactions(self, address: str, limit: int = 100, sort: str = "desc") -> List[dict]:
        """Get normal transactions."""
        r = self._call({
            "module": "account", "action": "txlist", "address": address,
            "startblock": 0, "endblock": 99999999, "offset": limit, "sort": sort
        })
        return r.get("result", []) if r.get("status") == "1" else []
    
    def get_internal_txs(self, address: str, limit: int = 100) -> List[dict]:
        """Get internal transactions (contract calls)."""
        r = self._call({
            "module": "account", "action": "txlistinternal", "address": address,
            "startblock": 0, "endblock": 99999999, "offset": limit, "sort": "desc"
        })
        return r.get("result", []) if r.get("status") == "1" else []
    
    def get_token_transfers(self, address: str, contract: str = None, limit: int = 100) -> List[dict]:
        """Get ERC20 token transfers."""
        params = {"module": "account", "action": "tokentx", "address": address, "offset": limit, "sort": "desc"}
        if contract:
            params["contractaddress"] = contract
        r = self._call(params)
        return r.get("result", []) if r.get("status") == "1" else []


class BlockchainMonitor:
    """Monitor addresses and generate alerts."""
    
    def __init__(self, citizen: str):
        self.citizen = citizen
        self.home = Path(f"/home/{citizen}")
        self.watch_file = self.home / "blockchain_watch.json"
        self.alerts_file = self.home / "blockchain_alerts.json"
        self.config = self._load()
        self._client = None
    
    def _load(self) -> dict:
        if self.watch_file.exists():
            try:
                return json.loads(self.watch_file.read_text())
            except:
                pass
        return {"addresses": {}, "last_check": {}, "min_eth": 0.1}
    
    def _save(self):
        self.watch_file.write_text(json.dumps(self.config, indent=2))
    
    def _client_get(self) -> EtherscanClient:
        if self._client is None:
            self._client = EtherscanClient()
        return self._client
    
    def add(self, address: str, label: str, notes: str = "") -> str:
        address = address.lower()
        self.config["addresses"][address] = {"label": label, "notes": notes, "added": now_iso(), "last_balance": None}
        self._save()
        return f"Added: {label} ({address[:10]}...)"
    
    def remove(self, address: str) -> str:
        address = address.lower()
        if address in self.config["addresses"]:
            label = self.config["addresses"][address]["label"]
            del self.config["addresses"][address]
            self._save()
            return f"Removed: {label}"
        return "Not found"
    
    def list_all(self) -> str:
        if not self.config["addresses"]:
            return "No addresses watched."
        lines = ["=== WATCH LIST ===", ""]
        for addr, info in self.config["addresses"].items():
            bal = info.get("last_balance")
            bal_str = f"{bal:.4f} ETH" if bal is not None else "?"
            lines.append(f"  {info['label']}: {bal_str}")
            lines.append(f"    {addr}")
            if info.get("notes"):
                lines.append(f"    Notes: {info['notes']}")
        return "\n".join(lines)
    
    def check_all(self) -> List[dict]:
        """Check all addresses, return alerts."""
        alerts = []
        client = self._client_get()
        min_eth = self.config.get("min_eth", 0.1)
        for addr, info in self.config["addresses"].items():
            try:
                bal = client.get_balance(addr)
                curr = bal.get("eth", 0)
                prev = info.get("last_balance")
                # Balance change alert
                if prev is not None:
                    diff = curr - prev
                    if abs(diff) >= min_eth:
                        alerts.append({
                            "type": "balance", "address": addr, "label": info["label"],
                            "change": diff, "new": curr, "time": now_iso()
                        })
                info["last_balance"] = curr
                # Transaction alerts
                txs = client.get_transactions(addr, limit=20)
                last_ts = self.config["last_check"].get(addr, 0)
                for tx in txs:
                    ts = int(tx.get("timeStamp", 0))
                    if ts <= last_ts:
                        continue
                    value = int(tx.get("value", 0)) / 1e18
                    if value < min_eth:
                        continue
                    is_out = tx.get("from", "").lower() == addr
                    other = tx.get("to") if is_out else tx.get("from")
                    alert = {
                        "type": "tx", "address": addr, "label": info["label"],
                        "direction": "OUT" if is_out else "IN", "eth": value,
                        "other": other, "hash": tx.get("hash"), "time": now_iso()
                    }
                    # Flag exchanges/mixers
                    if other:
                        other_low = other.lower()
                        if other_low in KNOWN_EXCHANGES:
                            alert["exchange"] = KNOWN_EXCHANGES[other_low]
                        if other_low in KNOWN_MIXERS:
                            alert["mixer"] = KNOWN_MIXERS[other_low]
                    alerts.append(alert)
                if txs:
                    self.config["last_check"][addr] = max(int(t.get("timeStamp", 0)) for t in txs)
            except Exception as e:
                alerts.append({"type": "error", "address": addr, "label": info["label"], "error": str(e)})
        self._save()
        if alerts:
            self._save_alerts(alerts)
        return alerts
    
    def _save_alerts(self, new: List[dict]):
        existing = []
        if self.alerts_file.exists():
            try:
                existing = json.loads(self.alerts_file.read_text())
            except:
                pass
        existing.extend(new)
        existing = existing[-500:]
        self.alerts_file.write_text(json.dumps(existing, indent=2))


def trace_funds(address: str, depth: int = 2, min_eth: float = 0.1) -> dict:
    """Trace outgoing fund movements."""
    client = EtherscanClient()
    visited = set()
    def trace(addr: str, d: int) -> dict:
        addr = addr.lower()
        result = {"address": addr, "flags": [], "out": []}
        if addr in KNOWN_EXCHANGES:
            result["flags"].append(f"EXCHANGE:{KNOWN_EXCHANGES[addr]}")
        if addr in KNOWN_MIXERS:
            result["flags"].append(f"MIXER:{KNOWN_MIXERS[addr]}")
        if d <= 0 or addr in visited:
            return result
        visited.add(addr)
        txs = client.get_transactions(addr, limit=100)
        for tx in txs:
            if tx.get("from", "").lower() != addr:
                continue
            value = int(tx.get("value", 0)) / 1e18
            if value < min_eth:
                continue
            to = tx.get("to", "")
            entry = {"to": to, "eth": value, "hash": tx.get("hash"), "ts": tx.get("timeStamp")}
            if to.lower() in KNOWN_EXCHANGES:
                entry["exchange"] = KNOWN_EXCHANGES[to.lower()]
            if to.lower() in KNOWN_MIXERS:
                entry["mixer"] = KNOWN_MIXERS[to.lower()]
            if d > 1 and to and "exchange" not in entry and "mixer" not in entry:
                entry["next"] = trace(to, d - 1)
            result["out"].append(entry)
        return result
    return trace(address, depth)


# =============================================================================
# Tool Functions
# =============================================================================

def blockchain_watch_add(args: dict, session: dict, modules: dict) -> str:
    address, label = args.get("address", ""), args.get("label", "Unknown")
    if not address or len(address) != 42:
        return "ERROR: Invalid address"
    return BlockchainMonitor(session["citizen"]).add(address, label, args.get("notes", ""))

def blockchain_watch_remove(args: dict, session: dict, modules: dict) -> str:
    address = args.get("address", "")
    if not address:
        return "ERROR: Address required"
    return BlockchainMonitor(session["citizen"]).remove(address)

def blockchain_watch_list(args: dict, session: dict, modules: dict) -> str:
    return BlockchainMonitor(session["citizen"]).list_all()

def blockchain_check(args: dict, session: dict, modules: dict) -> str:
    alerts = BlockchainMonitor(session["citizen"]).check_all()
    if not alerts:
        return "No new activity."
    lines = [f"=== {len(alerts)} ALERTS ==="]
    for a in alerts:
        if a["type"] == "balance":
            d = "↑" if a["change"] > 0 else "↓"
            lines.append(f"  {d} {a['label']}: {a['change']:+.4f} ETH (now {a['new']:.4f})")
        elif a["type"] == "tx":
            e = "📤" if a["direction"] == "OUT" else "📥"
            lines.append(f"  {e} {a['label']}: {a['direction']} {a['eth']:.4f} ETH")
            if a.get("exchange"):
                lines.append(f"      🏦 EXCHANGE: {a['exchange']}")
            if a.get("mixer"):
                lines.append(f"      ⚠️ MIXER: {a['mixer']}")
        elif a["type"] == "error":
            lines.append(f"  ❌ {a['label']}: {a['error']}")
    return "\n".join(lines)

def blockchain_trace(args: dict, session: dict, modules: dict) -> str:
    address = args.get("address", "")
    if not address:
        return "ERROR: Address required"
    try:
        result = trace_funds(address, args.get("depth", 2), args.get("min_eth", 0.1))
        return _format_trace(result, 0)
    except Exception as e:
        return f"ERROR: {e}"

def blockchain_balance(args: dict, session: dict, modules: dict) -> str:
    address = args.get("address", "")
    if not address:
        return "ERROR: Address required"
    try:
        r = EtherscanClient().get_balance(address)
        return f"Balance: {r['eth']:.6f} ETH"
    except Exception as e:
        return f"ERROR: {e}"

def blockchain_transactions(args: dict, session: dict, modules: dict) -> str:
    address = args.get("address", "")
    if not address:
        return "ERROR: Address required"
    try:
        client = EtherscanClient()
        txs = client.get_transactions(address, limit=args.get("limit", 20))
        if not txs:
            return "No transactions found."
        lines = [f"=== TRANSACTIONS ({address[:10]}...) ==="]
        for tx in txs:
            ts = datetime.fromtimestamp(int(tx.get("timeStamp", 0))).strftime("%m-%d %H:%M")
            value = int(tx.get("value", 0)) / 1e18
            is_out = tx.get("from", "").lower() == address.lower()
            d = "OUT" if is_out else "IN"
            other = tx.get("to") if is_out else tx.get("from")
            lines.append(f"  [{ts}] {d} {value:.4f} ETH → {other[:12]}...")
            if other and other.lower() in KNOWN_EXCHANGES:
                lines.append(f"    🏦 {KNOWN_EXCHANGES[other.lower()]}")
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR: {e}"

def _format_trace(t: dict, indent: int) -> str:
    lines = []
    p = "  " * indent
    lines.append(f"{p}{t['address'][:14]}...")
    for f in t.get("flags", []):
        lines.append(f"{p}  ⚠️ {f}")
    for o in t.get("out", [])[:10]:
        ts = datetime.fromtimestamp(int(o.get("ts", 0))).strftime("%m-%d") if o.get("ts") else "?"
        lines.append(f"{p}  → {o['eth']:.4f} ETH [{ts}] to {o['to'][:12]}...")
        if o.get("exchange"):
            lines.append(f"{p}    🏦 {o['exchange']}")
        if o.get("mixer"):
            lines.append(f"{p}    ⚠️ {o['mixer']}")
        if "next" in o:
            lines.append(_format_trace(o["next"], indent + 2))
    return "\n".join(lines)


BLOCKCHAIN_TOOL_DEFINITIONS = [
    {"name": "blockchain_watch_add", "description": "Add address to watch list",
     "input_schema": {"type": "object", "properties": {
         "address": {"type": "string"}, "label": {"type": "string"}, "notes": {"type": "string"}
     }, "required": ["address", "label"]}},
    {"name": "blockchain_watch_remove", "description": "Remove address from watch",
     "input_schema": {"type": "object", "properties": {"address": {"type": "string"}}, "required": ["address"]}},
    {"name": "blockchain_watch_list", "description": "List watched addresses",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "blockchain_check", "description": "Check watched addresses for activity",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "blockchain_trace", "description": "Trace fund movements (follow the money)",
     "input_schema": {"type": "object", "properties": {
         "address": {"type": "string"}, "depth": {"type": "integer"}, "min_eth": {"type": "number"}
     }, "required": ["address"]}},
    {"name": "blockchain_balance", "description": "Get ETH balance",
     "input_schema": {"type": "object", "properties": {"address": {"type": "string"}}, "required": ["address"]}},
    {"name": "blockchain_transactions", "description": "Get recent transactions",
     "input_schema": {"type": "object", "properties": {
         "address": {"type": "string"}, "limit": {"type": "integer"}
     }, "required": ["address"]}}
]
