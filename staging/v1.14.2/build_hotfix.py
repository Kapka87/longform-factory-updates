from pathlib import Path
import hashlib,json,zipfile,py_compile,tempfile

SRC=Path("packages/LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_1.lfupdate.zip")
OUT=Path("packages/LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_2.lfupdate.zip")

def sha(b): return hashlib.sha256(b).hexdigest()
if not SRC.exists(): raise SystemExit("missing v1.14.1 package")
with zipfile.ZipFile(SRC,"r") as z: files={n:z.read(n) for n in z.namelist()}

runner_names=[
 "payload/runners/en_story_production_media_v10.py",
 "payload/runners/jp_bts_production_media_v10.py",
 "payload/runners/en_bts_production_media_v10.py",
]
old='ffmpeg=shutil.which("ffmpeg"); ffprobe=shutil.which("ffprobe")'
new='ffmpeg=resolve_executable("ffmpeg"); ffprobe=resolve_executable("ffprobe")'
for n in runner_names:
    t=files[n].decode()
    if "from production_media_common_v10 import *" not in t and "from production_media_common_v10 import resolve_executable" not in t:
        raise SystemExit("runner common import missing: "+n)
    if old in t:
        t=t.replace(old,new,1)
    elif new not in t:
        raise SystemExit("ffmpeg resolver anchor missing: "+n)
    files[n]=t.encode()

boot="payload/control_center_v114_bootstrap.py"
bt=files[boot].decode().replace('FACTORY_VERSION="1.14.1"','FACTORY_VERSION="1.14.2"',1).replace('<div class="ver">v1.14.1</div>','<div class="ver">v1.14.2</div>',1)
files[boot]=bt.encode()

m=json.loads(files["update_manifest.json"])
m["package_id"]="LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_2"
m["version"]="1.14.2"
m["from_versions"]=["1.14.1"]
m["title"]="Four-Channel Production Integration · Runner Executable Path Hotfix"
m["summary"]="Ensures production media runners use the same macOS executable resolver as preflight."
for f in m["files"]:
    f["sha256"]=sha(files[f["source"]])
files["update_manifest.json"]=(json.dumps(m,ensure_ascii=False,indent=2)+"\n").encode()

notes=files.get("release_notes.md",b"").decode()
notes+="\n\n1.14.2 hotfix: EN_STORY, EN_BTS and JP_BTS production media runners now resolve ffmpeg/ffprobe using the shared Desktop-safe resolver instead of PATH-only shutil.which().\n"
files["release_notes.md"]=notes.encode()

with tempfile.TemporaryDirectory() as td:
    for fn in runner_names+[boot]:
        p=Path(td)/Path(fn).name; p.write_bytes(files[fn]); py_compile.compile(str(p),doraise=True)

with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
    for fn,b in files.items(): z.writestr(fn,b)

with zipfile.ZipFile(OUT) as z:
    assert z.testzip() is None
    mm=json.loads(z.read("update_manifest.json"))
    for f in mm["files"]:
        assert sha(z.read(f["source"]))==f["sha256"], f["source"]

digest=sha(OUT.read_bytes())
feed={
 "schema":"LONGFORM_FACTORY_UPDATE_FEED_v1",
 "generated_at":"AUTO",
 "channels":{"dev":{
   "version":"1.14.2",
   "package_url":"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_2.lfupdate.zip",
   "package_sha256":digest,
   "updater_api_min":"1.1",
   "published_at":"AUTO",
   "title":"Four-Channel Production Integration · Runner Executable Path Hotfix",
   "summary":"Fixes Desktop-app ffmpeg/ffprobe discovery during actual media runner execution."
 }},
 "cache_bust":"1.14.2-auto"
}
Path("feed.v1142.json").write_text(json.dumps(feed,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"bytes":OUT.stat().st_size,"sha256":digest},indent=2))

# trigger publish after workflow registration
