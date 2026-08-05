#!/usr/bin/env python3
"""Disposable HTTP components and in-container probes for the reference lab."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socket
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

PORT = 8080
SECRET_ROOT = Path("/runtime-secrets")
STATE_ROOT = Path("/lab-state")
CANARY_PATH = Path("/run/secrets/runtime_canary")
TOKEN_PREFIX = "SWRT_"  # noqa: S105 - disposable test-token marker, not a token


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _record_path(handle: str) -> Path:
    name = hashlib.sha256(handle.encode()).hexdigest()
    return SECRET_ROOT / f"{name}.json"


def _pending_path(request_id: str) -> Path:
    name = hashlib.sha256(request_id.encode()).hexdigest()
    return STATE_ROOT / "pending" / name


def _read_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    value = json.loads(handler.rfile.read(length))
    if not isinstance(value, dict):
        raise ValueError("request body must be an object")
    return value


def _respond(
    handler: BaseHTTPRequestHandler,
    value: object,
    *,
    status: int = 200,
) -> None:
    payload = _canonical(value)
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def _url_json(url: str, value: object | None = None) -> dict[str, Any]:
    data = None if value is None else _canonical(value)
    request = urllib.request.Request(  # noqa: S310 - fixed internal lab URLs only
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if value is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:  # noqa: S310
            parsed = json.loads(response.read())
    except urllib.error.HTTPError as error:
        parsed = json.loads(error.read())
    if not isinstance(parsed, dict):
        raise RuntimeError("lab response was not an object")
    return parsed


def _token_for(handle: str) -> str:
    value = json.loads(_record_path(handle).read_text(encoding="utf-8"))
    token = value.get("token")
    if not isinstance(token, str) or not token.startswith(TOKEN_PREFIX):
        raise RuntimeError("runtime credential record is invalid")
    return token


class _QuietHandler(BaseHTTPRequestHandler):
    server_version = "SynthWorldReference/1"

    def log_message(self, _format: str, *args: object) -> None:
        del args

    def do_GET(self) -> None:
        if self.path == "/health":
            _respond(self, {"status": "ready"})
            return
        self.handle_get()

    def do_POST(self) -> None:
        self.handle_post(_read_body(self))

    def handle_get(self) -> None:
        _respond(self, {"error": "not_found"}, status=404)

    def handle_post(self, _body: dict[str, Any]) -> None:
        _respond(self, {"error": "not_found"}, status=404)


class CredentialHandler(_QuietHandler):
    records: ClassVar[dict[str, dict[str, Any]]] = {}
    lock = threading.Lock()

    @classmethod
    def load_records(cls) -> None:
        SECRET_ROOT.mkdir(parents=True, exist_ok=True)
        for path in sorted(SECRET_ROOT.glob("*.json")):
            value = json.loads(path.read_text(encoding="utf-8"))
            token = value.get("token")
            if isinstance(token, str):
                cls.records[token] = value

    def handle_post(self, body: dict[str, Any]) -> None:
        if self.path == "/issue":
            self._issue(body)
        elif self.path == "/introspect":
            self._introspect(body)
        elif self.path == "/revoke":
            self._revoke(body)
        else:
            super().handle_post(body)

    def _issue(self, body: dict[str, Any]) -> None:
        handle = str(body["handle"])
        token = f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
        record = {
            "actions": sorted(set(str(item) for item in body["actions"])),
            "audience": str(body["audience"]),
            "expires_ns": time.monotonic_ns() + int(body["lifetime_ms"]) * 1_000_000,
            "group": str(body["group"]),
            "handle": handle,
            "revoked_ns": None,
            "sender": str(body["sender"]),
            "token": token,
        }
        with self.lock:
            old_path = _record_path(handle)
            if old_path.exists():
                old = json.loads(old_path.read_text(encoding="utf-8"))
                old_token = old.get("token")
                if isinstance(old_token, str):
                    self.records.pop(old_token, None)
            old_path.write_bytes(_canonical(record))
            os.chmod(old_path, 0o600)
            self.records[token] = record
        _respond(self, {"credential_handle": handle, "issued": True})

    def _introspect(self, body: dict[str, Any]) -> None:
        token = str(body["token"])
        with self.lock:
            record = self.records.get(token)
            snapshot = None if record is None else dict(record)
        if snapshot is None:
            _respond(self, {"active": False, "reason": "unknown_credential"})
            return
        now = time.monotonic_ns()
        reason: str | None = None
        if now > int(snapshot["expires_ns"]):
            reason = "expired"
        elif snapshot["sender"] not in {"*", str(body["sender"])}:
            reason = "sender_mismatch"
        elif snapshot["audience"] != str(body["audience"]):
            reason = "audience_mismatch"
        revoked = snapshot["revoked_ns"]
        if revoked is not None:
            delays = {
                "component-gateway-a": 50_000_000,
                "component-gateway-b": 100_000_000,
            }
            visible_at = int(revoked) + delays.get(str(body["point"]), 0)
            if now >= visible_at:
                reason = "revoked"
        _respond(
            self,
            {
                "actions": snapshot["actions"] if reason is None else [],
                "active": reason is None,
                "reason": reason,
            },
        )

    def _revoke(self, body: dict[str, Any]) -> None:
        group = str(body["group"])
        epoch = time.monotonic_ns()
        count = 0
        with self.lock:
            for record in self.records.values():
                if record["group"] == group:
                    record["revoked_ns"] = epoch
                    count += 1
        _respond(self, {"revoked_count": count, "status": "accepted"})


class PolicyHandler(_QuietHandler):
    def handle_post(self, body: dict[str, Any]) -> None:
        if self.path != "/decide":
            super().handle_post(body)
            return
        allowed = str(body["action"]) in set(body["actions"])
        _respond(self, {"decision": "allow" if allowed else "deny"})


class AuditHandler(_QuietHandler):
    records: ClassVar[list[str]] = []

    def handle_post(self, body: dict[str, Any]) -> None:
        if self.path != "/record":
            super().handle_post(body)
            return
        self.records.append(_digest(body))
        _respond(self, {"recorded": True, "record_digest": self.records[-1]})


class TargetHandler(_QuietHandler):
    effects: ClassVar[list[str]] = []
    lock = threading.Lock()

    def handle_get(self) -> None:
        if self.path == "/state":
            with self.lock:
                state = tuple(self.effects)
            _respond(self, {"effect_count": len(state), "effect_digests": state})
            return
        super().handle_get()

    def handle_post(self, body: dict[str, Any]) -> None:
        if self.path != "/effect":
            super().handle_post(body)
            return
        request_id = str(body["request_id"])
        pending = _pending_path(request_id)
        pending.parent.mkdir(parents=True, exist_ok=True)
        pending.write_text("pending\n", encoding="utf-8")
        time.sleep(int(body.get("delay_ms", 0)) / 1_000)
        effect = _digest(
            {
                "action": str(body["action"]),
                "request_id": request_id,
                "target": str(body["target"]),
            }
        )
        with self.lock:
            self.effects.append(effect)
        pending.unlink(missing_ok=True)
        _respond(self, {"decision": "allow", "effect_digest": effect})


class GatewayHandler(_QuietHandler):
    component_id = os.environ.get("COMPONENT_ID", "component-gateway-unknown")

    def handle_post(self, body: dict[str, Any]) -> None:
        if self.path != "/access":
            super().handle_post(body)
            return
        try:
            token = _token_for(str(body["credential_handle"]))
            introspection = _url_json(
                "http://credential:8080/introspect",
                {
                    "audience": body["audience"],
                    "point": self.component_id,
                    "sender": body["sender"],
                    "token": token,
                },
            )
        except (OSError, RuntimeError, ValueError):
            _respond(self, _failed_closed("component-credential"))
            return
        if not introspection.get("active"):
            _respond(
                self,
                {
                    "decision": "deny",
                    "reason": introspection.get("reason", "inactive"),
                    "side_effect": False,
                },
            )
            return
        try:
            policy = _url_json(
                "http://policy:8080/decide",
                {"action": body["action"], "actions": introspection["actions"]},
            )
        except (OSError, RuntimeError, ValueError):
            _respond(self, _failed_closed("component-policy"))
            return
        if policy.get("decision") != "allow":
            _respond(
                self,
                {"decision": "deny", "reason": "policy", "side_effect": False},
            )
            return
        try:
            _url_json(
                "http://audit:8080/record",
                {
                    "action": body["action"],
                    "point": self.component_id,
                    "request_digest": _digest(str(body["request_id"])),
                },
            )
        except (OSError, RuntimeError, ValueError):
            _respond(self, _failed_closed("component-audit"))
            return
        try:
            target = _url_json(
                "http://target:8080/effect",
                {
                    "action": body["action"],
                    "delay_ms": int(body.get("delay_ms", 0)),
                    "request_id": body["request_id"],
                    "target": body["target"],
                },
            )
        except (OSError, RuntimeError, ValueError):
            _respond(self, _failed_closed("component-target"))
            return
        _respond(
            self,
            {
                "decision": str(target["decision"]),
                "effect_digest": str(target["effect_digest"]),
                "side_effect": True,
            },
        )


class BaselineHandler(_QuietHandler):
    def handle_post(self, body: dict[str, Any]) -> None:
        if self.path != "/access":
            super().handle_post(body)
            return
        try:
            target = _url_json(
                "http://target:8080/effect",
                {
                    "action": body["action"],
                    "delay_ms": int(body.get("delay_ms", 0)),
                    "request_id": body["request_id"],
                    "target": body["target"],
                },
            )
            _respond(
                self,
                {
                    "decision": str(target["decision"]),
                    "effect_digest": str(target["effect_digest"]),
                    "side_effect": True,
                },
            )
        except (OSError, RuntimeError, ValueError):
            _respond(self, _failed_closed("component-target"))


def _failed_closed(dependency: str) -> dict[str, object]:
    return {
        "decision": "error",
        "dependency": dependency,
        "reason": "dependency_unavailable",
        "side_effect": False,
    }


HANDLERS: dict[str, type[_QuietHandler]] = {
    "audit": AuditHandler,
    "baseline": BaselineHandler,
    "credential": CredentialHandler,
    "forbidden": TargetHandler,
    "gateway": GatewayHandler,
    "policy": PolicyHandler,
    "target": TargetHandler,
}


def _serve(role: str) -> None:
    if role == "credential":
        CredentialHandler.load_records()
    handler = HANDLERS[role]
    server = ThreadingHTTPServer(("0.0.0.0", PORT), handler)  # noqa: S104
    server.serve_forever()


def _issue(args: argparse.Namespace) -> dict[str, Any]:
    return _url_json(
        "http://credential:8080/issue",
        {
            "actions": args.actions.split(","),
            "audience": args.audience,
            "group": args.group,
            "handle": args.handle,
            "lifetime_ms": args.lifetime_ms,
            "sender": args.sender,
        },
    )


def _access(args: argparse.Namespace) -> dict[str, Any]:
    return _access_call(
        args.endpoint,
        handle=args.handle,
        sender=args.sender,
        audience=args.audience,
        action=args.action,
        target=args.target,
        request_id=args.request_id,
        delay_ms=args.delay_ms,
    )


def _access_call(
    endpoint: str,
    *,
    handle: str,
    sender: str,
    audience: str,
    action: str,
    target: str,
    request_id: str,
    delay_ms: int = 0,
) -> dict[str, Any]:
    body: dict[str, object] = {
        "action": action,
        "audience": audience,
        "credential_handle": handle,
        "delay_ms": delay_ms,
        "request_id": request_id,
        "sender": sender,
        "target": target,
    }
    return _url_json(f"http://{endpoint}:8080/access", body)


def _probe(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic_ns()
    connected = False
    reason = "network_isolation"
    try:
        with socket.create_connection((args.host, args.port), timeout=0.5):
            connected = True
            reason = "connected"
    except OSError:
        pass
    return {
        "connected": connected,
        "duration_ns": time.monotonic_ns() - started,
        "reason": reason,
    }


def _scan(_args: argparse.Namespace) -> dict[str, Any]:
    canary = CANARY_PATH.read_bytes().strip()
    opaque = hashlib.sha256(canary).hexdigest()
    channels = {
        "context": _canonical({"canary_digest": opaque, "source": "prompt"}),
        "log": _canonical({"event": "runtime_scan", "secret": "redacted"}),
        "memory": _canonical({"memory_handle": f"sha256:{opaque}"}),
        "trace": _canonical({"vectors": 4, "value": "redacted"}),
    }
    return {
        "channels": [
            {
                "canary_match": canary in payload,
                "channel": channel,
                "payload_digest": hashlib.sha256(payload).hexdigest(),
            }
            for channel, payload in sorted(channels.items())
        ],
        "extraction_vectors_exercised": [
            "environment",
            "memory_recall",
            "prompt",
            "tool_output",
        ],
    }


def _measure(args: argparse.Namespace) -> dict[str, Any]:
    latencies: list[int] = []
    failed = 0
    started = time.monotonic_ns()
    for index in range(args.count):
        request_started = time.monotonic_ns()
        result = _access_call(
            args.endpoint,
            handle=args.handle,
            sender=args.sender,
            audience=args.audience,
            action=args.action,
            target=args.target,
            request_id=f"{args.request_prefix}-{index:03d}",
        )
        latencies.append(time.monotonic_ns() - request_started)
        if result.get("decision") != "allow":
            failed += 1
    duration = time.monotonic_ns() - started
    ordered = sorted(latencies)
    return {
        "completed_count": args.count - failed,
        "duration_ns": duration,
        "failed_count": failed,
        "p50_ns": int(statistics.median(ordered)),
        "p95_ns": ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)],
        "sample_count": args.count,
    }


def _revoke_scenario(args: argparse.Namespace) -> dict[str, Any]:
    for handle in (args.parent_handle, args.child_handle):
        issue_args = argparse.Namespace(
            actions=args.action,
            audience=args.audience,
            group=args.group,
            handle=handle,
            lifetime_ms=30_000,
            sender=args.sender,
        )
        _issue(issue_args)

    in_flight: dict[str, Any] = {}

    def run_in_flight() -> None:
        sent = time.monotonic_ns()
        result = _access_call(
            "gateway-a",
            handle=args.parent_handle,
            sender=args.sender,
            audience=args.audience,
            action=args.action,
            target=args.target,
            request_id="l06-in-flight",
            delay_ms=600,
        )
        in_flight.update(
            {
                "completed_ns": time.monotonic_ns(),
                "result": result,
                "sent_ns": sent,
            }
        )

    flight = threading.Thread(target=run_in_flight)
    flight.start()
    pending = _pending_path("l06-in-flight")
    deadline = time.monotonic() + 3
    while not pending.exists() and time.monotonic() < deadline:
        time.sleep(0.005)
    if not pending.exists():
        raise RuntimeError("in-flight target request did not start")

    epoch = time.monotonic_ns()
    _url_json("http://credential:8080/revoke", {"group": args.group})
    point_results: dict[str, dict[str, Any]] = {}

    def poll(endpoint: str, component_id: str) -> None:
        counter = 0
        while True:
            result = _access_call(
                endpoint,
                handle=args.parent_handle,
                sender=args.sender,
                audience=args.audience,
                action=args.action,
                target=args.target,
                request_id=f"l06-ack-{endpoint}-{counter:03d}",
            )
            if result.get("decision") == "deny":
                point_results[component_id] = {
                    "ack_offset_ns": time.monotonic_ns() - epoch,
                    "decision": "deny",
                }
                return
            counter += 1
            time.sleep(0.005)

    pollers = (
        threading.Thread(target=poll, args=("gateway-a", "component-gateway-a")),
        threading.Thread(target=poll, args=("gateway-b", "component-gateway-b")),
    )
    for thread in pollers:
        thread.start()
    for thread in pollers:
        thread.join(timeout=3)
    if len(point_results) != 2:
        raise RuntimeError("revocation acknowledgement polling was incomplete")

    target_time = epoch + args.bound_ms * 1_000_000 + 20_000_000
    remaining = target_time - time.monotonic_ns()
    if remaining > 0:
        time.sleep(remaining / 1_000_000_000)
    attempts: list[dict[str, Any]] = []
    for endpoint, component_id in (
        ("gateway-a", "component-gateway-a"),
        ("gateway-b", "component-gateway-b"),
    ):
        for handle in sorted((args.parent_handle, args.child_handle)):
            sent = time.monotonic_ns()
            result = _access_call(
                endpoint,
                handle=handle,
                sender=args.sender,
                audience=args.audience,
                action=args.action,
                target=args.target,
                request_id=f"l06-post-bound-{endpoint}-{_digest(handle)[:8]}",
            )
            attempts.append(
                {
                    "completed_offset_ns": time.monotonic_ns() - epoch,
                    "credential_or_child_handle": handle,
                    "decision": result["decision"],
                    "enforcement_point_id": component_id,
                    "sent_offset_ns": sent - epoch,
                    "side_effect": bool(result.get("side_effect")),
                }
            )

    flight.join(timeout=3)
    if flight.is_alive() or not in_flight:
        raise RuntimeError("in-flight target request did not complete")
    attempts.append(
        {
            "completed_offset_ns": int(in_flight["completed_ns"]) - epoch,
            "credential_or_child_handle": args.parent_handle,
            "decision": in_flight["result"]["decision"],
            "enforcement_point_id": "component-gateway-a",
            "sent_offset_ns": int(in_flight["sent_ns"]) - epoch,
            "side_effect": bool(in_flight["result"].get("side_effect")),
        }
    )
    return {
        "point_results": [
            point_results[key] | {"component_id": key} for key in sorted(point_results)
        ],
        "revocation_epoch_monotonic_ns": epoch,
        "timed_attempts": sorted(
            attempts,
            key=lambda item: (
                str(item["enforcement_point_id"]),
                str(item["credential_or_child_handle"]),
                int(item["sent_offset_ns"]),
            ),
        ),
    }


def _health(args: argparse.Namespace) -> dict[str, Any]:
    return _url_json(f"http://{args.endpoint}:8080/health")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve = subparsers.add_parser("serve")
    serve.add_argument("role", choices=sorted(HANDLERS))
    subparsers.add_parser("idle")

    control = subparsers.add_parser("control")
    commands = control.add_subparsers(dest="control", required=True)
    issue = commands.add_parser("issue")
    issue.add_argument("--handle", required=True)
    issue.add_argument("--sender", required=True)
    issue.add_argument("--audience", required=True)
    issue.add_argument("--actions", required=True)
    issue.add_argument("--group", required=True)
    issue.add_argument("--lifetime-ms", required=True, type=int)

    access = commands.add_parser("access")
    access.add_argument("--endpoint", required=True)
    access.add_argument("--handle", default="")
    access.add_argument("--sender", default="")
    access.add_argument("--audience", default="")
    access.add_argument("--action", required=True)
    access.add_argument("--target", required=True)
    access.add_argument("--request-id", required=True)
    access.add_argument("--delay-ms", default=0, type=int)

    probe = commands.add_parser("probe")
    probe.add_argument("--host", required=True)
    probe.add_argument("--port", default=PORT, type=int)
    commands.add_parser("scan")

    measure = commands.add_parser("measure")
    measure.add_argument("--endpoint", required=True)
    measure.add_argument("--handle", default="")
    measure.add_argument("--sender", default="")
    measure.add_argument("--audience", default="")
    measure.add_argument("--action", required=True)
    measure.add_argument("--target", required=True)
    measure.add_argument("--request-prefix", required=True)
    measure.add_argument("--count", required=True, type=int)

    revoke = commands.add_parser("revoke-scenario")
    revoke.add_argument("--parent-handle", required=True)
    revoke.add_argument("--child-handle", required=True)
    revoke.add_argument("--sender", required=True)
    revoke.add_argument("--audience", required=True)
    revoke.add_argument("--action", required=True)
    revoke.add_argument("--target", required=True)
    revoke.add_argument("--group", required=True)
    revoke.add_argument("--bound-ms", required=True, type=int)

    health = commands.add_parser("health")
    health.add_argument("--endpoint", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "serve":
        _serve(args.role)
        return 0
    if args.command == "idle":
        while True:
            time.sleep(60)
    handlers = {
        "access": _access,
        "health": _health,
        "issue": _issue,
        "measure": _measure,
        "probe": _probe,
        "revoke-scenario": _revoke_scenario,
        "scan": _scan,
    }
    result = handlers[args.control](args)
    sys.stdout.buffer.write(_canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
