from pathlib import Path
import hashlib,json,zipfile,py_compile,tempfile

SRC=Path("packages/LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_3.lfupdate.zip")
OUT=Path("packages/LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_4.lfupdate.zip")
def sha(b): return hashlib.sha256(b).hexdigest()
if not SRC.exists(): raise SystemExit("missing v1.14.3 package")
with zipfile.ZipFile(SRC,"r") as z: files={n:z.read(n) for n in z.namelist()}

def ensure_resolver(name):
    t=files[name].decode()
    if "def resolve_executable(name):" not in t:
        markers=["def _latest(folder,pattern):","def _read(path,default=None):","def now():"]
        marker=next((m for m in markers if m in t),None)
        if not marker: raise SystemExit("resolver anchor missing: "+name)
        ins="""def resolve_executable(name):
    import os
    found = shutil.which(name)
    if found:
        return found
    for candidate in (f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}", f"/opt/local/bin/{name}"):
        p = Path(candidate)
        if p.is_file() and os.access(str(p), os.X_OK):
            return str(p)
    return None

"""
        idx=t.find(marker); t=t[:idx]+ins+t[idx:]
    t=t.replace('shutil.which("ffmpeg")', 'resolve_executable("ffmpeg")')
    t=t.replace('shutil.which("ffprobe")', 'resolve_executable("ffprobe")')
    files[name]=t.encode()

for name in ["payload/adapters/channels/production_adapter_common_v10.py","payload/runners/production_media_common_v10.py"]:
    if name in files: ensure_resolver(name)
    else: print("SKIP_MISSING",name)

for name in ["payload/runners/en_story_production_media_v10.py","payload/runners/en_bts_production_media_v10.py","payload/runners/jp_bts_production_media_v10.py"]:
    t=files[name].decode()
    if 'from production_media_common_v10 import *' in t or "from production_media_common_v10 import resolve_executable" in t:
        t=t.replace('shutil.which("ffmpeg")', 'resolve_executable("ffmpeg")').replace('shutil.which("ffprobe")', 'resolve_executable("ffprobe")')
    files[name]=t.encode()

boot="payload/control_center_v114_bootstrap.py"
bt=files[boot].decode().replace('FACTORY_VERSION="1.14.0"','FACTORY_VERSION="1.14.4"').replace('FACTORY_VERSION="1.14.1"','FACTORY_VERSION="1.14.4"').replace('FACTORY_VERSION="1.14.2"','FACTORY_VERSION="1.14.4"').replace('FACTORY_VERSION="1.14.3"','FACTORY_VERSION="1.14.4"')
bt=bt.replace('<div class="ver">v1.14.0</div>','<div class="ver">v1.14.4</div>').replace('<div class="ver">v1.14.1</div>','<div class="ver">v1.14.4</div>').replace('<div class="ver">v1.14.2</div>','<div class="ver">v1.14.4</div>').replace('<div class="ver">v1.14.3</div>','<div class="ver">v1.14.4</div>')
files[boot]=bt.encode()

m=json.loads(files["update_manifest.json"])
m["package_id"]="LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_4"
m["version"]="1.14.4"
m["from_versions"]=["1.14.3"]
m["title"]="Four-Channel Production Integration · Shared Executable Resolver Hotfix"
m["summary"]="Applies the Desktop-safe ffmpeg/ffprobe resolver consistently to both Production Preflight and media runners."
for f in m["files"]: f["sha256"]=sha(files[f["source"]])
files["update_manifest.json"]=(json.dumps(m,ensure_ascii=False,indent=2)+"\n").encode()
notes=files.get("release_notes.md",b"").decode()+"\n\n1.14.4 hotfix: shared executable resolution is applied to both adapter preflight and production runner modules so Desktop-app execution finds macOS Homebrew ffmpeg/ffprobe consistently.\n"
files["release_notes.md"]=notes.encode()

with tempfile.TemporaryDirectory() as td:
    for name in files:
        if name.endswith(".py"):
            q=Path(td)/Path(name).name; q.write_bytes(files[name]); py_compile.compile(str(q),doraise=True)
with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
    for name,b in files.items(): z.writestr(name,b)
with zipfile.ZipFile(OUT) as z:
    assert z.testzip() is None
    mm=json.loads(z.read("update_manifest.json"))
    for f in mm["files"]: assert sha(z.read(f["source"]))==f["sha256"],f["source"]
    for req in ["payload/adapters/channels/production_adapter_common_v10.py","payload/runners/production_media_common_v10.py"]:
        if req in files: assert "def resolve_executable(name):" in z.read(req).decode()
digest=sha(OUT.read_bytes())
feed={"schema":"LONGFORM_FACTORY_UPDATE_FEED_v1","generated_at":"AUTO","channels":{"dev":{"version":"1.14.4","package_url":"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_4.lfupdate.zip","package_sha256":digest,"updater_api_min":"1.1","published_at":"AUTO","title":"Four-Channel Production Integration · Shared Executable Resolver Hotfix","summary":"Fixes Desktop-app ffmpeg/ffprobe discovery in both production preflight and runners."}},"cache_bust":"1.14.4-auto"}
Path("feed.v1144.json").write_text(json.dumps(feed,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"bytes":OUT.stat().st_size,"sha256":digest},indent=2))
# trigger v1.14.4 publish
