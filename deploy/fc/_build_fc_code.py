import os, zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(ROOT))  # pan-radar/
OUT = os.path.join(ROOT, "code.zip")

# 进包内容：后端主程序、配置、启动脚本 + 前端 web/（FC 同源托管，免公开桶/CORS）
files = {
    "panradar.py": os.path.join(PROJ, "panradar.py"),
    "config.json": os.path.join(PROJ, "config.json"),
    "bootstrap": os.path.join(ROOT, "bootstrap"),
}
# web/ 下所有文件（config.js 保持空 API_BASE，FC 同源）
web_dir = os.path.join(PROJ, "web")
for dirpath, _, names in os.walk(web_dir):
    for n in names:
        full = os.path.join(dirpath, n)
        rel = "web/" + os.path.relpath(full, web_dir).replace("\\", "/")
        files[rel] = full

if os.path.exists(OUT):
    os.remove(OUT)

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for name, src in files.items():
        if not os.path.exists(src):
            raise SystemExit("缺少文件: " + src)
        info = zipfile.ZipInfo(name)
        if name == "bootstrap":
            info.external_attr = (0o100755 & 0xFFFF) << 16
        else:
            info.external_attr = (0o100644 & 0xFFFF) << 16
        with open(src, "rb") as f:
            z.writestr(info, f.read())

with zipfile.ZipFile(OUT) as z:
    print("包内文件数:", len(z.infolist()))
    for i in z.infolist():
        print("  %-22s mode=%o" % (i.filename, (i.external_attr >> 16) & 0xFFFF))

print("OK ->", OUT, "(%d bytes)" % os.path.getsize(OUT))
