#!/usr/bin/env python3
"""Proxy that fixes LM Studio's OpenAI-compatibility gap for tool calls.

LM Studio 2.51.0 returns a tool call as tagged text in `message.content` when
`tool_choice` is "auto" (the value LangChain/Deep Agents uses), leaving
`message.tool_calls` empty. Hosted providers return the call in `tool_calls`.
This proxy forwards to LM Studio and moves the parsed call into `tool_calls`,
so the agent can run unmodified. The model is NOT modified or replaced.

    python tools/lmstudio_shim.py                 # serve on :1235 -> LM Studio :1234
    python tools/lmstudio_shim.py --selftest      # offline parser tests, no server

Point the lab at it with AZURE_OPENAI_ENDPOINT=http://host.docker.internal:1235/v1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

UPSTREAM = os.environ.get("SHIM_UPSTREAM", "http://127.0.0.1:1234")

# Some templates carry zero-width characters inside the tags; ignore them.
ZERO_WIDTH = {ord(c): None for c in "\u200b\u200d\u2060\ufeff"}
# The template teaches an opening tag + JSON + closing tag, but this model
# actually emits the JSON object followed only by a CLOSING tag, with no opening
# tag. Match on the closing tag and take the JSON immediately before it, which
# covers both forms. Nested braces work because the match must end at a `}` that
# is immediately followed by the closing tag.
BLOCK = re.compile(r"(\{.*?\})\s*<\s*/\s*tool_call\s*>", re.S)
# Orphaned opening tags left behind after the blocks are removed.
STRAY_TAG = re.compile(r"<\s*/?\s*tool_call\s*>")


def extract_tool_calls(content):
    """Return (tool_calls, leftover_text). Returns ([], content) if this is not a tool call.

    Bails out entirely on any malformed block: a model that merely talks about
    XML must never be rewritten.
    """
    if not content:
        return [], content
    cleaned = content.translate(ZERO_WIDTH)
    blocks = list(BLOCK.finditer(cleaned))
    if not blocks:
        return [], content

    calls = []
    for m in blocks:
        try:
            payload = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            return [], content
        if not isinstance(payload, dict) or "name" not in payload:
            return [], content
        args = payload.get("arguments", {})
        if isinstance(args, dict):
            args_text = json.dumps(args, ensure_ascii=False)
        elif isinstance(args, str):
            args_text = args
        else:
            return [], content
        digest = hashlib.sha1(f"{payload['name']}{args_text}".encode()).hexdigest()[:12]
        calls.append({
            "id": f"call_{digest}",
            "type": "function",
            "function": {"name": payload["name"], "arguments": args_text},
        })

    leftover = cleaned
    for m in reversed(blocks):
        leftover = leftover[:m.start()] + leftover[m.end():]
    leftover = STRAY_TAG.sub("", leftover).strip()
    return calls, (leftover or None)


def normalize(payload):
    """Move tagged calls into tool_calls. Returns True if the payload changed."""
    changed = False
    for choice in payload.get("choices", []):
        msg = choice.get("message") or {}
        if msg.get("tool_calls"):          # already structured: pass through untouched
            continue
        calls, leftover = extract_tool_calls(msg.get("content"))
        if calls:
            msg["tool_calls"] = calls
            msg["content"] = leftover
            choice["message"] = msg
            changed = True
    return changed


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/") in ("/health", "/v1/health"):
            self._send(200, json.dumps({"status": "ok", "upstream": UPSTREAM}).encode())
            return
        self._proxy("GET", None)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            self._send(400, b'{"error": {"message": "invalid JSON body"}}')
            return
        if body.get("stream"):
            body["stream"] = False       # SSE frames would need the same fix per chunk
        self._proxy("POST", json.dumps(body).encode())

    def _proxy(self, method, payload):
        headers = {"Content-Type": "application/json"}
        auth = self.headers.get("Authorization")     # forwarded, never logged
        if auth:
            headers["Authorization"] = auth
        req = Request(UPSTREAM.rstrip("/") + self.path, data=payload,
                      headers=headers, method=method)
        try:
            with urlopen(req, timeout=900) as r:
                data, code = r.read(), r.status
        except HTTPError as e:
            data, code = e.read(), e.code
        except URLError as e:
            self._send(502, json.dumps(
                {"error": {"message": f"upstream unreachable: {e.reason}"}}).encode())
            return

        if code == 200 and method == "POST":
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict) and normalize(parsed):
                data = json.dumps(parsed, ensure_ascii=False).encode()
        self._send(code, data)

    def log_message(self, fmt, *args):
        sys.stderr.write("[shim] " + (fmt % args) + "\n")


# Tags built from codepoints so the fixtures survive copy/paste through editors
# that strip zero-width characters. The model emits the closing tag WITH a
# zero-width space after "<"; OPEN is the plain documented form.
ZWSP = chr(0x200B)
OPEN = "<tool_call>"
CLOSE = "</" + ZWSP + "tool_call>"
PLAIN_CLOSE = "</tool_call>"


def _selftest() -> int:
    cases = []

    # 1. The model's REAL observed output: bare JSON, newline, closing tag only.
    calls, left = extract_tool_calls(
        '{"name": "ls", "arguments": {"path": "workspace/"}}\n' + CLOSE)
    cases.append(("observed output parsed", len(calls) == 1
                  and calls[0]["function"]["name"] == "ls"
                  and json.loads(calls[0]["function"]["arguments"]) == {"path": "workspace/"}
                  and left is None))

    # 2. The full documented form, opening tag included.
    calls, left = extract_tool_calls(
        OPEN + '{"name": "ls", "arguments": {"path": "workspace/"}}' + CLOSE)
    cases.append(("full tag form parsed", len(calls) == 1 and left is None))

    # 3. Nested braces inside arguments.
    calls, _ = extract_tool_calls(
        '{"name": "write_file", "arguments": {"content": "{\\"a\\": 1}"}}' + CLOSE)
    cases.append(("nested braces", len(calls) == 1
                  and json.loads(calls[0]["function"]["arguments"]) == {"content": '{"a": 1}'}))

    # 4. Two calls in one reply.
    calls, _ = extract_tool_calls(
        '{"name": "a", "arguments": {}}' + CLOSE
        + '\n{"name": "b", "arguments": {"x": 1}}' + CLOSE)
    cases.append(("two calls parsed", [c["function"]["name"] for c in calls] == ["a", "b"]))

    # 5. Plain closing tag without the zero-width space.
    calls, _ = extract_tool_calls('{"name": "ls", "arguments": {}}' + PLAIN_CLOSE)
    cases.append(("zero-width tag parsed", len(calls) == 1))

    # 6. Prose before the call is kept as content.
    calls, left = extract_tool_calls(
        'I will check.\n{"name": "ls", "arguments": {}}' + CLOSE)
    cases.append(("leading prose kept", left == "I will check." and len(calls) == 1))

    # 7. Prose that merely mentions the tag must NOT be rewritten.
    calls, left = extract_tool_calls("I looked at the " + OPEN + " tag in the docs.")
    cases.append(("prose untouched", calls == [] and left is not None))

    # 8. Malformed JSON in a block must NOT be rewritten.
    calls, left = extract_tool_calls("{not json}" + CLOSE)
    cases.append(("malformed block untouched", calls == [] and left is not None))

    # 9. Plain prose reply passes through with no calls.
    calls, left = extract_tool_calls("The files are answer.json and sales.csv.")
    cases.append(("plain prose untouched", calls == [] and left is not None))

    # 10. An already-structured payload is never rewritten.
    structured = {"choices": [{"message": {"content": None,
                                           "tool_calls": [{"id": "x", "type": "function",
                                                           "function": {"name": "ls", "arguments": "{}"}}]}}]}
    cases.append(("already structured untouched", normalize(structured) is False))

    # 11. normalize() moves a real observed call into tool_calls.
    fixed = {"choices": [{"message": {
        "content": '{"name": "ls", "arguments": {"path": "workspace/"}}' + "\n" + CLOSE}}]}
    ok = (normalize(fixed)
          and fixed["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "ls"
          and fixed["choices"][0]["message"]["content"] is None)
    cases.append(("normalize moves the call", ok))

    # 12. normalize() leaves a prose reply alone.
    prose = {"choices": [{"message": {"content": "just talking"}}]}
    cases.append(("normalize leaves prose", normalize(prose) is False))

    failed = [name for name, ok in cases if not ok]
    for name, ok in cases:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    print(f"{len(cases) - len(failed)}/{len(cases)} passed")
    return 1 if failed else 0


def main() -> int:
    global UPSTREAM
    ap = argparse.ArgumentParser(description="LM Studio tool-call compatibility proxy")
    ap.add_argument("--port", type=int, default=1235)
    ap.add_argument("--upstream", default=UPSTREAM)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    UPSTREAM = a.upstream
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), Handler)   # 0.0.0.0 so Docker can reach it
    print(f"shim listening on :{a.port} -> {UPSTREAM}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())