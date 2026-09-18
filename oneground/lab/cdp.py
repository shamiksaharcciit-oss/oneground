"""A very small DevTools-protocol client, on the standard library only.

Why this exists: task 024's proof drove the lab over HTTP and task 024b took
screenshots, and the landing page still hung for the developer on both
workdirs. A request that returns 200 says nothing about whether the script
that consumes it ran, and a screenshot says nothing about why it did not. To
see that, something has to hold the page open, run JavaScript in it, and read
what the browser recorded -- which is what the DevTools protocol is for.

It is deliberately not a browser-automation framework. It speaks just enough
websocket to send `Runtime.evaluate` and to collect `Runtime.exceptionThrown`
and `Runtime.consoleAPICalled`, so a test can assert that a real page reached
a real state, with no new dependency and nothing to install wherever the suite
runs. No oneground code imports it at run time; it is a test and diagnosis
tool, and `oneground lab` never loads it.
"""

import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

EDGE_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/microsoft-edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
)


def find_browser():
    """A Chromium-family browser, or None where there is none."""
    for name in ("msedge", "google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    for path in EDGE_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class WebSocket:
    """Text frames over a client websocket. Enough for the protocol, no more."""

    def __init__(self, url, timeout=30):
        _, _, rest = url.partition("://")
        hostport, _, path = rest.partition("/")
        host, _, port = hostport.partition(":")
        self.sock = socket.create_connection((host, int(port or 80)), timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            .encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise OSError("the browser closed the connection")
            buf += chunk
        if b"101" not in buf.split(b"\r\n", 1)[0]:
            raise OSError(f"websocket upgrade refused: {buf[:120]!r}")
        self._rest = buf.split(b"\r\n\r\n", 1)[1]

    def _recv(self, n):
        while len(self._rest) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise OSError("the browser closed the connection")
            self._rest += chunk
        out, self._rest = self._rest[:n], self._rest[n:]
        return out

    def send(self, text):
        payload = text.encode()
        header = bytearray([0x81])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        mask = os.urandom(4)
        header += mask
        self.sock.sendall(bytes(header) +
                          bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def recv(self):
        while True:
            b0, b1 = self._recv(2)
            opcode = b0 & 0x0F
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._recv(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._recv(8))[0]
            data = self._recv(n)
            if opcode == 0x8:                      # close
                raise OSError("the browser closed the socket")
            if opcode == 0x9:                      # ping -> pong
                continue
            if opcode in (0x1, 0x2):
                return data.decode("utf-8", "replace")

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class Browser:
    """A headless Chromium-family browser, driven over the protocol."""

    def __init__(self, binary=None, width=1200, height=900, timeout=60):
        self.binary = binary or find_browser()
        if not self.binary:
            raise RuntimeError("no Chromium-family browser found")
        self.port = _free_port()
        self.profile = tempfile.mkdtemp(prefix="oneground-lab-cdp-")
        self.timeout = timeout
        self.proc = subprocess.Popen(
            [self.binary, "--headless=new", "--disable-gpu", "--no-first-run",
             "--no-default-browser-check", "--disable-extensions",
             "--disable-background-networking", "--disable-sync",
             "--disable-dev-shm-usage", "--no-sandbox",
             f"--window-size={width},{height}",
             f"--user-data-dir={self.profile}",
             f"--remote-debugging-port={self.port}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws = WebSocket(self._target(), timeout)
        self._id = 0
        self.errors = []      # uncaught exceptions, as the page saw them
        self.console = []     # console.* calls
        self.call("Runtime.enable")
        self.call("Page.enable")

    def _target(self):
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            try:
                raw = urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/json/list", timeout=2).read()
                for t in json.loads(raw):
                    if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                        return t["webSocketDebuggerUrl"]
            except (urllib.error.URLError, OSError, ValueError):
                pass
            time.sleep(0.1)
        raise RuntimeError("the browser never opened a debugging port")

    def call(self, method, **params):
        self._id += 1
        wanted = self._id
        self.ws.send(json.dumps({"id": wanted, "method": method,
                                 "params": params}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("method") == "Runtime.exceptionThrown":
                d = message["params"]["exceptionDetails"]
                self.errors.append(
                    (d.get("exception", {}).get("description")
                     or d.get("text", "")).split("\n")[0])
            elif message.get("method") == "Runtime.consoleAPICalled":
                p = message["params"]
                self.console.append(
                    p["type"] + ": " + " ".join(
                        str(a.get("value", a.get("description", "")))
                        for a in p.get("args", [])))
            elif message.get("id") == wanted:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})

    def goto(self, url):
        self.call("Page.navigate", url=url)

    def evaluate(self, expression):
        """Run an expression in the page and return its JSON value."""
        result = self.call("Runtime.evaluate", expression=expression,
                           returnByValue=True, awaitPromise=True)
        if result.get("exceptionDetails"):
            d = result["exceptionDetails"]
            raise RuntimeError(d.get("exception", {}).get("description")
                               or d.get("text", "evaluate failed"))
        return result.get("result", {}).get("value")

    def wait_for(self, expression, timeout=20, interval=0.15):
        """Poll an expression until it is truthy. Returns whether it became so."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.evaluate(expression):
                    return True
            except RuntimeError:
                pass
            time.sleep(interval)
        return False

    def text(self, selector):
        return self.evaluate(
            "(() => { const e = document.querySelector(" + json.dumps(selector)
            + "); return e ? e.textContent.trim() : null; })()")

    def screenshot(self, path, full=True):
        data = self.call("Page.captureScreenshot", format="png",
                         captureBeyondViewport=bool(full))["data"]
        with open(path, "wb") as f:
            f.write(base64.b64decode(data))
        return path

    def close(self):
        try:
            self.ws.close()
        finally:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=15)
            except Exception:
                self.proc.kill()
            shutil.rmtree(self.profile, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
