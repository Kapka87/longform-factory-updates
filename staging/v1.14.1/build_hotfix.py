from pathlib import Path
import hashlib,json,zipfile,py_compile,tempfile

SRC=Path("packages/LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_0_r3.lfupdate.zip")
OUT=Path("packages/LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_1.lfupdate.zip")
def sha(b): return hashlib.sha256(b).hexdigest()
if not SRC.exists(): raise SystemExit("missing r3 package")
with zipfile.ZipFile(SRC,"r") as z: files={n:z.read(n) for n in z.namelist()}
common_name="payload/adapters/channels/production_adapter_common_v10.py"
common=files[common_name].decode()
if "def resolve_executable(name):" not in common:
    anchor="def _latest(folder,pattern):"
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
    idx=common.find(anchor)
    if idx<0: raise SystemExit("common anchor missing")
    common=common[:idx]+ins+common[idx:]
common=common.replace('shutil.which("ffmpeg")),"detail":shutil.which("ffmpeg") or "missing"', 'resolve_executable("ffmpeg")),"detail":resolve_executable("ffmpeg") or "missing"')
common=common.replace('shutil.which("ffprobe")),"detail":shutil.which("ffprobe") or "missing"', 'resolve_executable("ffprobe")),"detail":resolve_executable("ffprobe") or "missing"')
files[common_name]=common.encode()
for n in ["payload/runners/en_story_production_media_v10.py","payload/runners/jp_bts_production_media_v10.py"]:
    t=files[n].decode()
    t=t.replace('shutil.which("ffmpeg"); ffprobe=shutil.which("ffprobe")', 'resolve_executable("ffmpeg"); ffprobe=resolve_executable("ffprobe")')
    files[n]=t.encode()
n="payload/runners/en_bts_production_media_v10.py"
t=files[n].decode()
if "from production_media_common_v10 import resolve_executable" not in t:
    anchor="import numpy as np\n"
    t=t.replace(anchor,anchor+"\nROOT_FILE=Path(__file__).resolve().parent\nif str(ROOT_FILE) not in sys.path: sys.path.insert(0,str(ROOT_FILE))\nfrom production_media_common_v10 import resolve_executable\n")
t=t.replace('shutil.which("ffmpeg"); ffprobe=shutil.which("ffprobe")', 'resolve_executable("ffmpeg"); ffprobe=resolve_executable("ffprobe")')
files[n]=t.encode()
boot="payload/control_center_v114_bootstrap.py"
bt=files[boot].decode().replace('FACTORY_VERSION="1.14.0"','FACTORY_VERSION="1.14.1"',1).replace('<div class="ver">v1.14.0</div>','<div class="ver">v1.14.1</div>',1)
files[boot]=bt.encode()
m=json.loads(files["update_manifest.json"])
m["package_id"]="LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_1"
m["version"]="1.14.1"
m["from_versions"]=["1.14.0"]
m["title"]="Four-Channel Production Integration · FFmpeg Path Hotfix"
m["summary"]="Fixes Desktop-app execution environments that omit Homebrew paths when resolving ffmpeg and ffprobe."
for f in m["files"]:
    f["sha256"]=sha(files[f["source"]])
files["update_manifest.json"]=(json.dumps(m,ensure_ascii=False,indent=2)+"\n").encode()
notes=files.get("release_notes.md",b"").decode()+"\n\n1.14.1 hotfix: Production adapters and media runners now resolve ffmpeg/ffprobe from PATH plus standard macOS Homebrew paths (/opt/homebrew/bin, /usr/local/bin, /opt/local/bin).\n"
files["release_notes.md"]=notes.encode()
with tempfile.TemporaryDirectory() as td:
    for fn in [common_name,"payload/runners/en_story_production_media_v10.py","payload/runners/jp_bts_production_media_v10.py","payload/runners/en_bts_production_media_v10.py",boot]:
        q=Path(td)/Path(fn).name; q.write_bytes(files[fn]); py_compile.compile(str(q),doraise=True)
with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
    for fn,b in files.items(): z.writestr(fn,b)
with zipfile.ZipFile(OUT) as z:
    assert z.testzip() is None
    mm=json.loads(z.read("update_manifest.json"))
    for f in mm["files"]: assert sha(z.read(f["source"]))==f["sha256"], f["source"]
digest=sha(OUT.read_bytes())
feed={"schema":"LONGFORM_FACTORY_UPDATE_FEED_v1","generated_at":"AUTO","channels":{"dev":{"version":"1.14.1","package_url":"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_1.lfupdate.zip","package_sha256":digest,"updater_api_min":"1.1","published_at":"AUTO","title":"Four-Channel Production Integration · FFmpeg Path Hotfix","summary":"Fixes Desktop-app ffmpeg/ffprobe discovery for production QA and render."}},"cache_bust":"1.14.1-auto"}
Path("feed.v1141.json").write_text(json.dumps(feed,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"bytes":OUT.stat().st_size,"sha256":digest},indent=2))