#!/usr/bin/env python3
"""Styled screenshots of the Tickerlens dev server.

Headless Chrome on this VM cannot load external CDNs, so we build Tailwind
CSS locally with the standalone CLI and inject it. This renders exactly what
a real browser with working CDNs would show.

Usage:
    python3 scripts/screenshot.py [outdir] [shot...]

Self-heals: installs Chrome if missing, rebuilds CSS, starts the server if down.
"""
import os
import subprocess
import sys
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.expanduser("~/workspace/tools")
CHROME_DEB_URL = "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"
TWCSS_URL = ("https://github.com/tailwindlabs/tailwindcss/releases/"
             "download/v3.4.13/tailwindcss-linux-x64")
BASE = "http://127.0.0.1:8123"

SHOTS = {
    "home": "/",
    "aapl-overview": "/company/AAPL",
    "aapl-detail": "/company/AAPL/detail",
    "aapl-compare": "/company/AAPL/compare",
    "aapl-vs-msft": "/company/AAPL/vs/MSFT",
}


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)


def ensure_chrome():
    if sh("which google-chrome").returncode == 0:
        return
    print("installing chrome...")
    deb = "/tmp/chrome.deb"
    subprocess.run(["curl", "-sL", "-o", deb, CHROME_DEB_URL], check=True)
    sh(f"dpkg -i {deb}")
    sh("apt-get install -f -y")
    assert sh("which google-chrome").returncode == 0, "chrome install failed"


def ensure_twcss():
    tw = os.path.join(TOOLS, "twcss")
    if not (os.path.isfile(tw) and os.access(tw, os.X_OK)):
        os.makedirs(TOOLS, exist_ok=True)
        print("downloading tailwind cli...")
        subprocess.run(["curl", "-sL", "-o", tw, TWCSS_URL], check=True)
        os.chmod(tw, 0o755)
    return tw


def build_css(tw):
    css_in = "/tmp/tw_input.css"
    css_out = "/tmp/tw_app.css"
    with open(css_in, "w") as f:
        f.write("@tailwind base; @tailwind components; @tailwind utilities;\n")
    r = sh(f'{tw} -i {css_in} -o {css_out} '
           f'--content "{REPO}/src/tickerlens/templates/**/*.html"')
    assert os.path.isfile(css_out), f"css build failed: {r.stderr[:300]}"
    # sanity: the build must contain responsive variants used across templates
    with open(css_out) as f:
        css = f.read()
    assert "md\\:hidden" in css or "md:hidden" in css, \
        "css build looks incomplete (no md:hidden)"
    return css


def ensure_server():
    try:
        urllib.request.urlopen(BASE + "/", timeout=5).getcode()
        return
    except Exception:
        pass
    print("starting server...")
    log = open("/tmp/uvicorn-shots.log", "ab")
    subprocess.Popen(
        [f"{REPO}/.venv/bin/python", "-m", "uvicorn", "tickerlens.main:app",
         "--port", "8123"],
        cwd=REPO, stdout=log, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(30):
        time.sleep(1)
        try:
            if urllib.request.urlopen(BASE + "/", timeout=5).getcode() == 200:
                return
        except Exception:
            pass
    raise RuntimeError("server did not start")


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
        "~/workspace/tickerlens-shots")
    wanted = sys.argv[2:] or list(SHOTS)
    os.makedirs(outdir, exist_ok=True)

    ensure_chrome()
    ensure_server()
    css = build_css(ensure_twcss())

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome",
                              args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        for name in wanted:
            path = SHOTS.get(name)
            if not path:
                print(f"unknown shot {name}, skipping")
                continue
            try:
                pg.goto(BASE + path, wait_until="domcontentloaded", timeout=60000)
                pg.add_style_tag(content=css)
                pg.wait_for_timeout(1200)
                pg.screenshot(path=os.path.join(outdir, f"{name}.png"))
                print("OK", name)
            except Exception as e:
                print("FAIL", name, str(e)[:120])
        b.close()


if __name__ == "__main__":
    main()
