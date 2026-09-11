# -*- coding: utf-8 -*-
"""重启 pan-radar 服务：杀掉占用端口的旧进程树。"""
import subprocess, sys, re, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PORT = "8931"
out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                     errors="replace").stdout
pids = set()
for line in out.splitlines():
    if "LISTENING" in line and re.search(r"[:\]]%s\s" % PORT, line):
        pid = line.split()[-1]
        if pid.isdigit() and pid != "0":
            pids.add(pid)
print("监听 %s 的进程:", pids or "无")
for pid in pids:
    r = subprocess.run(["taskkill", "/F", "/T", "/PID", pid],
                       capture_output=True, text=True, errors="replace")
    print("kill %s -> %s %s" % (pid, r.returncode, (r.stdout or r.stderr).strip()[:120]))
print("done")
