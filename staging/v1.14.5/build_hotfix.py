from pathlib import Path
import hashlib,json,zipfile,py_compile,tempfile

SRC=Path("packages/LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_4.lfupdate.zip")
OUT=Path("packages/LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_5.lfupdate.zip")
def sha(b): return hashlib.sha256(b).hexdigest()
if not SRC.exists(): raise SystemExit("missing v1.14.4 package")
with zipfile.ZipFile(SRC,"r") as z: files={n:z.read(n) for n in z.namelist()}

common="payload/adapters/channels/production_adapter_common_v10.py"
if common not in files: raise SystemExit("missing production adapter common")
t=files[common].decode()
if "def resolve_executable(name):" not in t:
    marker="def _latest(folder,pattern):"
    if marker not in t: raise SystemExit("adapter common resolver anchor missing")
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
    t=t.replace(marker,ins+marker,1)
t=t.replace('shutil.which("ffmpeg")', 'resolve_executable("ffmpeg")').replace('shutil.which("ffprobe")', 'resolve_executable("ffprobe")')
files[common]=t.encode()

en_adapter="payload/adapters/channels/en_bts/production_adapter_v11.py"
if en_adapter not in files: raise SystemExit("missing EN_BTS adapter")
t=files[en_adapter].decode()
if "def resolve_executable(name):" not in t:
    marker="class "
    idx=t.find(marker)
    if idx < 0: raise SystemExit("EN_BTS adapter class anchor missing")
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
    t=t[:idx]+ins+t[idx:]
t=t.replace('shutil.which("ffmpeg")', 'resolve_executable("ffmpeg")').replace('shutil.which("ffprobe")', 'resolve_executable("ffprobe")')
files[en_adapter]=t.encode()

en_runner="payload/runners/en_bts_production_media_v10.py"
if en_runner not in files: raise SystemExit("missing EN_BTS runner")
t=files[en_runner].decode()
if "resolve_executable(" not in t:
    # Import shared resolver into the runner.
    anchor="import numpy as np\n"
    imp="from pathlib import Path\nimport sys\n"+anchor+"ROOT_FILE=Path(__file__).resolve().parent\nif str(ROOT_FILE) not in sys.path: sys.path.insert(0,str(ROOT_FILE))\nfrom production_media_common_v10 import resolve_executable\n"
    if "import numpy as np\n" not in t: raise SystemExit("EN_BTS runner numpy anchor missing")
    t=t.replace("import numpy as np\n",imp,1)
t=t.replace('shutil.which("ffmpeg")', 'resolve_executable("ffmpeg")').replace('shutil.which("ffprobe")', 'resolve_executable("ffprobe")')
files[en_runner]=t.encode()

boot="payload/control_center_v114_bootstrap.py"
bt=files[boot].decode()
for v in ["1.14.0","1.14.1","1.14.2","1.14.3","1.14.4"]:
    bt=bt.replace(f'FACTORY_VERSION="{v}"','FACTORY_VERSION="1.14.5"',1)
for v in ["1.14.0","1.14.1","1.14.2","1.14.3","1.14.4"]:
    bt=bt.replace(f'<div class="ver">v{v}</div>','<div class="ver">v1.14.5</div>',1)
files[boot]=bt.encode()

m=json.loads(files["update_manifest.json"])
m["package_id"]="LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_5"
m["version"]="1.14.5"
m["from_versions"]=["1.14.4"]
m["title"]="Four-Channel Production Integration · EN_BTS Executable Resolver Hotfix"
m["summary"]="Fixes EN_BTS production preflight and runner executable resolution under the Desktop app environment."
for f in m["files"]: f["sha256"]=sha(files[f["source"]])
files["update_manifest.json"]=(json.dumps(m,ensure_ascii=False,indent=2)+"\n").encode()
notes=files.get("release_notes.md",b"").decode()+"\n\n1.14.5 hotfix: EN_BTS production_adapter_v11 and media runner now use the shared Desktop-safe ffmpeg/ffprobe resolver.\n"
files["release_notes.md"]=notes.encode()

with tempfile.TemporaryDirectory() as td:
    for n in [common,en_adapter,en_runner,boot]:
        p=Path(td)/Path(n).name; p.write_bytes(files[n]); py_compile.compile(str(p),doraise=True)
with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
    for n,b in files.items(): z.writestr(n,b)
with zipfile.ZipFile(OUT) as z:
    assert z.testzip() is None
    mm=json.loads(z.read("update_manifest.json"))
    for f in mm["files"]: assert sha(z.read(f["source"]))==f["sha256"],f["source"]
    assert 'resolve_executable("ffmpeg")' in z.read(en_adapter).decode()
    assert 'resolve_executable("ffprobe")' in z.read(en_adapter).decode()
    assert 'resolve_executable("ffmpeg")' in z.read(en_runner).decode()
    assert 'resolve_executable("ffprobe")' in z.read(en_runner).decode()
digest=sha(OUT.read_bytes())
feed={"schema":"LONGFORM_FACTORY_UPDATE_FEED_v1","generated_at":"AUTO","channels":{"dev":{"version":"1.14.5","package_url":"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_5.lfupdate.zip","package_sha256":digest,"updater_api_min":"1.1","published_at":"AUTO","title":"Four-Channel Production Integration · EN_BTS Executable Resolver Hotfix","summary":"Fixes EN_BTS production preflight and runner ffmpeg/ffprobe discovery."}},"cache_bust":"1.14.5-auto"}
Path("feed.v1145.json").write_text(json.dumps(feed,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"bytes":OUT.stat().st_size,"sha256":digest},indent=2))
# trigger v1.14.5 publish

# deterministic publish trigger
