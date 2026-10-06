"""Screenshot a running Streamlit page through Chrome's DevTools protocol.

Plain `chrome --headless --screenshot` can capture only Streamlit's loading
skeleton, because the app renders over a websocket after the page loads. This
opens the page, waits, optionally scrolls the lead pane, then captures.
Needs only `websockets`, which the venv already has.

    .venv/bin/python docs/assets/src/shoot.py URL OUT.png [--scale 2] [--scroll 0]
"""
import argparse
import base64
import json
import subprocess
import tempfile
import time
import urllib.request

from websockets.sync.client import connect

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9333

# Scrolls the lead pane (the scrollable ancestor of the score line) by N px.
SCROLL_JS = """(n => {
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let t;
  while ((t = w.nextNode())) {
    if (t.nodeValue.includes('Points per signal')) {
      for (let e = t.parentElement; e; e = e.parentElement) {
        if (e.scrollHeight > e.clientHeight + 5 && getComputedStyle(e).overflowY !== 'visible') {
          e.scrollTop = n;
          return 'scrolled ' + e.tagName;
        }
      }
    }
  }
  return 'no scrollable pane';
})(%d)"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("out")
    ap.add_argument("--scale", type=float, default=2)
    ap.add_argument("--scroll", type=int, default=0, help="px to scroll the lead pane")
    ap.add_argument("--wait", type=float, default=14, help="seconds to let the app render")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    a = ap.parse_args()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        proc = subprocess.Popen(
            [CHROME, "--headless=new", f"--remote-debugging-port={PORT}",
             f"--user-data-dir={profile}", "--hide-scrollbars",
             f"--window-size={a.width},{a.height}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            tabs = None
            for _ in range(50):
                try:
                    tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
                    break
                except (OSError, ValueError):
                    time.sleep(0.3)
            if tabs is None:
                raise SystemExit("Chrome did not start")
            ws_url = next(t for t in tabs if t["type"] == "page")["webSocketDebuggerUrl"]
            with connect(ws_url, max_size=None) as ws:
                n = 0

                def call(method, **params):
                    nonlocal n
                    n += 1
                    ws.send(json.dumps({"id": n, "method": method, "params": params}))
                    while True:
                        m = json.loads(ws.recv())
                        if m.get("id") == n:
                            return m.get("result", m)

                call("Emulation.setDeviceMetricsOverride", width=a.width, height=a.height,
                     deviceScaleFactor=a.scale, mobile=False)
                call("Page.navigate", url=a.url)
                time.sleep(a.wait)
                if a.scroll:
                    print(call("Runtime.evaluate", expression=SCROLL_JS % a.scroll)["result"].get("value"))
                    time.sleep(2)
                data = call("Page.captureScreenshot", format="png")["data"]
            with open(a.out, "wb") as f:
                f.write(base64.b64decode(data))
            print("wrote", a.out)
        finally:
            proc.terminate()
            proc.wait(timeout=10)


if __name__ == "__main__":
    main()
