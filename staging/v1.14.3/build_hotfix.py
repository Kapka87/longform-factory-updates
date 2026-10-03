from pathlib import Path
import hashlib,json,zipfile,py_compile,tempfile

SRC=Path("packages/LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_0_r3.lfupdate.zip")
OUT=Path("packages/LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_5.lfupdate.zip")
def sha(b): return hashlib.sha256(b).hexdigest()
if not SRC.exists(): raise SystemExit("missing 1.14.4 package")
with zipfile.ZipFile(SRC,"r") as z: files={n:z.read(n) for n in z.namelist()}
common_name="payload/runners/production_media_common_v10.py"
common=files[common_name].decode()
if "def resolve_executable(name):" not in common:
    marker="def now():"
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
    idx=common.find(marker)
    if idx<0: raise SystemExit("common resolver anchor missing")
    common=common[:idx]+ins+common[idx:]
files[common_name]=common.encode()
boot="payload/control_center_v114_bootstrap.py"
bt=files[boot].decode().replace('FACTORY_VERSION="1.14.0"','FACTORY_VERSION="1.14.5"',1).replace('FACTORY_VERSION="1.14.2"','FACTORY_VERSION="1.14.5"',1)
bt=bt.replace('<div class="ver">v1.14.0</div>','<div class="ver">v1.14.5</div>',1).replace('<div class="ver">v1.14.2</div>','<div class="ver">v1.14.5</div>',1)
files[boot]=bt.encode()
m=json.loads(files["update_manifest.json"])
m["package_id"]="LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_3"
m["version"]="1.14.5"
m["from_versions"]=["1.14.2"]
m["title"]="Four-Channel Production Integration · Shared Executable Resolver Fix"
m["summary"]="Fixes the actual media runner executable resolution by defining the Desktop-safe ffmpeg/ffprobe resolver in the shared media runtime module."
for f in m["files"]: f["sha256"]=sha(files[f["source"]])
files["update_manifest.json"]=(json.dumps(m,ensure_ascii=False,indent=2)+"\n").encode()
notes=files.get("release_notes.md",b"").decode()+"\n\n1.14.5 hotfix: production_media_common_v10 now defines resolve_executable(), shared by production runners, including standard macOS Homebrew locations.\n"
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
feed={"schema":"LONGFORM_FACTORY_UPDATE_FEED_v1","generated_at":"AUTO","channels":{"dev":{"version":"1.14.5","package_url":"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_3.lfupdate.zip","package_sha256":digest,"updater_api_min":"1.1","published_at":"AUTO","title":"Four-Channel Production Integration · Shared Executable Resolver Fix","summary":"Fixes actual media runner ffmpeg/ffprobe resolution in Desktop execution."}},"cache_bust":"1.14.5-auto"}
Path("feed.v1143.json").write_text(json.dumps(feed,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"bytes":OUT.stat().st_size,"sha256":digest},indent=2))
# trigger v1.14.5 publish

# trigger proven publisher for v1.14.5

# trigger v1.14.5 after publish-workflow fix
