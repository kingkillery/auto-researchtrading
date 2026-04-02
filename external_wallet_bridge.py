from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>External Wallet Orders</title><style>
:root{color-scheme:dark;--bg:#07111f;--panel:#0c1b2ef2;--line:#94a3b81f;--text:#e8eef7;--muted:#8fa3bd;--accent:#45d0a1;--warn:#d7b35d;--danger:#f17c7c;--info:#79b8ff;font-family:"Segoe UI","Inter",sans-serif}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top left,#27f0c029,transparent 28%),linear-gradient(180deg,#081322,#050b13);color:var(--text)}.shell{max-width:1200px;margin:0 auto;padding:24px}.hero,.card{border:1px solid var(--line);border-radius:24px;background:var(--panel);padding:20px}.hero{margin-bottom:16px}.list{display:grid;gap:14px}.req{border:1px solid var(--line);border-radius:18px;padding:16px;background:#040c15b8}.top,.row,.footer,.actions{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}.metrics{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}.pill{padding:5px 9px;border-radius:999px;border:1px solid #ffffff14;font-size:.82rem}.pending{color:var(--warn)}.approved{color:var(--info)}.rejected{color:var(--danger)}.submitted,.handled{color:var(--accent)}button{border:0;border-radius:999px;padding:8px 12px;font-weight:700;cursor:pointer}.approve{background:var(--info);color:#041018}.reject{background:var(--danger);color:#180607}.submit{background:var(--accent);color:#041018}.refresh{background:#17304d;color:var(--text)}code,pre{display:block;white-space:pre-wrap;word-break:break-word;background:#0000002a;border:1px solid var(--line);border-radius:12px;padding:10px;margin-top:10px}.muted{color:var(--muted);line-height:1.5}ul{margin:10px 0 0 18px;padding:0}.note{margin-top:10px;color:var(--muted)}.meta{font-size:.92rem;color:var(--muted)}</style></head><body><div class="shell"><section class="hero"><h1>External wallet order board</h1><p class="muted">This is the manual-signature handoff for Jupiter live mode. Review the normalized signer payload, approve or reject it, submit it through the wallet-controlled Jupiter surface, then mark it submitted so the queue stays operationally clean.</p><div class="metrics" id="summary"></div></section><section class="card"><div class="footer"><strong id="count">Loading...</strong><span class="muted" id="path"></span><button class="refresh" onclick="load()">Refresh</button></div><div class="list" id="requests"></div></section></div><script>
function esc(v){return String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')}
function badgeClass(status){return ['approved','rejected','submitted','handled'].includes(status)?status:'pending'}
function metricsHtml(data){const counts=data.status_counts||{};return ['pending','approved','rejected','submitted','handled','info_only'].map(k=>`<span class="pill ${badgeClass(k)}">${k}: ${counts[k]||0}</span>`).join('')}
function decisionButtons(r){if(r.approval_status==='submitted'){return ''}return `<div class="actions"><button class="approve" onclick="decide('${r.request_id}','approved')">Approve</button><button class="reject" onclick="decide('${r.request_id}','rejected')">Reject</button><button class="submit" onclick="decide('${r.request_id}','submitted')">Mark submitted</button></div>`}
async function load(){const res=await fetch('/api/requests',{cache:'no-store'});const data=await res.json();document.getElementById('count').textContent=`${data.pending_count} pending requests`;document.getElementById('path').textContent=data.request_path;document.getElementById('summary').innerHTML=metricsHtml(data);const mount=document.getElementById('requests');mount.innerHTML=(data.requests||[]).map(r=>`<div class="req"><div class="top"><strong>${esc(r.asset)} ${esc(r.action)} ${esc(r.side||'')}</strong><span class="pill ${badgeClass(r.approval_status)}">${esc(r.approval_status)}</span></div><div class="row meta"><span>Request ID</span><strong>${esc(r.request_id)}</strong></div><div class="row"><span>Wallet</span><strong>${esc(r.wallet_address||'n/a')}</strong></div><div class="row"><span>Target</span><strong>${esc(r.target_position_usd)}</strong></div><div class="row"><span>Delta</span><strong>${esc(r.size_delta_usd)}</strong></div><div class="row"><span>Timestamp</span><strong>${esc(r.timestamp)}</strong></div><p class="muted">${esc(r.operator_summary||r.message||'')}</p><div class="muted"><strong>Checklist</strong><ul>${(r.handoff?.checklist||[]).map(item=>`<li>${esc(item)}</li>`).join('')}</ul></div>${decisionButtons(r)}${r.latest_decision?.note?`<div class="note"><strong>Latest note:</strong> ${esc(r.latest_decision.note)}</div>`:''}<code>${esc(JSON.stringify(r.signer_payload||r,null,2))}</code></div>`).join('');}
async function decide(requestId,decision){const note=window.prompt(`Optional note for ${decision}:`,'')||'';await fetch('/api/decision',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:requestId,decision,note})});await load();}
load();
</script></body></html>"""

ALLOWED_DECISIONS = {"approved", "rejected", "submitted", "handled"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")


class ExternalWalletBoard:
    def __init__(self, request_path: Path):
        self.request_path = request_path
        self.decision_path = request_path.with_suffix(".decisions.jsonl")
        self.legacy_ack_path = request_path.with_suffix(".acks.jsonl")

    def requests(self) -> dict[str, Any]:
        requests = [self._normalize_request(row, index=index) for index, row in enumerate(read_jsonl(self.request_path))]
        latest_decisions = self._latest_decisions()
        enriched = []
        for row in requests:
            decision = latest_decisions.get(row["request_id"])
            approval_status = row.get("approval_status") or "pending"
            if decision is not None:
                approval_status = str(decision.get("decision") or approval_status)
            row = {
                **row,
                "approval_status": approval_status,
                "latest_decision": decision,
            }
            enriched.append(row)

        counts = Counter(row["approval_status"] for row in enriched)
        return {
            "request_path": str(self.request_path),
            "decision_path": str(self.decision_path),
            "pending_count": counts.get("pending_manual_signature", 0) + counts.get("pending", 0),
            "status_counts": {
                "pending": counts.get("pending_manual_signature", 0) + counts.get("pending", 0),
                "approved": counts.get("approved", 0),
                "rejected": counts.get("rejected", 0),
                "submitted": counts.get("submitted", 0),
                "handled": counts.get("handled", 0),
                "info_only": counts.get("info_only", 0),
            },
            "requests": list(reversed(enriched)),
        }

    def decide(self, request_id: str, decision: str, note: str | None = None) -> dict[str, Any]:
        if decision not in ALLOWED_DECISIONS:
            raise ValueError(f"unsupported decision {decision!r}")
        payload = {
            "request_id": request_id,
            "decision": decision,
            "note": (note or "").strip(),
            "timestamp": int(time.time()),
        }
        append_jsonl(self.decision_path, payload)
        return {"status": "ok", **payload}

    def ack(self, request_id: str) -> dict[str, Any]:
        payload = {"request_id": request_id, "decision": "handled", "timestamp": int(time.time())}
        append_jsonl(self.legacy_ack_path, payload)
        append_jsonl(self.decision_path, payload)
        return {"status": "ok", **payload}

    def _normalize_request(self, row: dict[str, Any], *, index: int) -> dict[str, Any]:
        request_id = str(
            row.get("request_id")
            or f"{row.get('timestamp', 'na')}::{row.get('asset', 'na')}::{row.get('action', 'na')}::{index}"
        )
        approval_status = str(row.get("approval_status") or "pending_manual_signature")
        if approval_status == "pending_manual_signature":
            approval_status = "pending"
        return {
            **row,
            "request_id": request_id,
            "approval_status": approval_status,
        }

    def _latest_decisions(self) -> dict[str, dict[str, Any]]:
        decisions: dict[str, dict[str, Any]] = {}
        for row in read_jsonl(self.decision_path):
            request_id = str(row.get("request_id") or "")
            if request_id:
                decisions[request_id] = row
        for row in read_jsonl(self.legacy_ack_path):
            request_id = str(row.get("request_id") or "")
            if request_id and request_id not in decisions:
                decisions[request_id] = {"request_id": request_id, "decision": "handled", "timestamp": row.get("timestamp")}
        return decisions


def handler_factory(board: ExternalWalletBoard):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            route = urlparse(self.path).path
            if route == "/":
                self._send(HTTPStatus.OK, HTML.encode("utf-8"), "text/html; charset=utf-8")
                return
            if route == "/api/requests":
                self._send_json(HTTPStatus.OK, board.requests())
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            route = urlparse(self.path).path
            content_length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
            payload = json.loads(raw.decode("utf-8"))
            request_id = str(payload.get("request_id") or "")
            if not request_id:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "request_id_required"})
                return

            if route == "/api/ack":
                self._send_json(HTTPStatus.OK, board.ack(request_id))
                return
            if route == "/api/decision":
                decision = str(payload.get("decision") or "")
                note = str(payload.get("note") or "")
                try:
                    response = board.decide(request_id, decision, note)
                except ValueError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                self._send_json(HTTPStatus.OK, response)
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

        def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            self._send(status, json.dumps(payload, sort_keys=True).encode("utf-8"), "application/json")

        def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Approval board for external-wallet Jupiter order requests")
    parser.add_argument("--request-path", required=True, help="Path to the JSONL request file emitted by run_jupiter_live.py")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    board = ExternalWalletBoard(Path(args.request_path))
    server = ThreadingHTTPServer((args.host, args.port), handler_factory(board))
    print(f"external wallet board listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
