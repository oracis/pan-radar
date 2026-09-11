# -*- coding: utf-8 -*-
"""抽出 index.html 里的内联 JS，交给 node 做语法校验。"""
import os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HTML = os.path.join(ROOT, "web", "index.html")
NODE = r"C:\Users\DELL\.workbuddy\binaries\node\versions\22.22.2-3\node.exe"

html = open(HTML, encoding="utf-8").read()
blocks = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S | re.I)
js = "\n;\n".join(blocks)
out = os.path.join(HERE, "_inline.js")
open(out, "w", encoding="utf-8").write(js)

r = subprocess.run([NODE, "--check", out], capture_output=True, text=True)
print("blocks:", len(blocks), "chars:", len(js))
print("exit:", r.returncode)
print(r.stdout[-2000:])
print(r.stderr[-3000:])
