from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, zipfile, py_compile, tempfile

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/"packages"/"LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_0_r2.lfupdate.zip"
OUT=ROOT/"packages"/"LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_0_r3.lfupdate.zip"

def sha_bytes(b): return hashlib.sha256(b).hexdigest()
def sha_file(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

BOOTSTRAP=r'''#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import os, runpy, sys

ROOT=Path(os.environ.get("LONGFORM_FACTORY_ROOT",str(Path.home()/"Desktop"/"KohoroAudition"/"LongformFactory_v1_Production"))).expanduser().resolve()
qa_dir=ROOT/"factory"/"qa"
if str(qa_dir) not in sys.path:
    sys.path.insert(0,str(qa_dir))

src=ROOT/"factory"/"control_center_current.py"
text=src.read_text(encoding="utf-8")
if 'FACTORY_VERSION="1.13.0"' in text:
    text=text.replace('FACTORY_VERSION="1.13.0"','FACTORY_VERSION="1.14.0"',1)
elif 'FACTORY_VERSION="1.14.0"' not in text:
    raise RuntimeError("v1.14 bootstrap runtime-version anchor missing")

text=text.replace('if channel=="JP_STORY" and str(m.get("schema_version"))=="1.2":','if str(m.get("schema_version"))=="1.2":',1)

imp='from four_channel_production_integration import four_channel_production_status, run_four_channel_production_qa\n'
anchor='from cross_channel_media_smoke import media_smoke_status, run_media_smoke\n'
if imp.strip() not in text:
    if anchor not in text:
        raise RuntimeError("v1.14 bootstrap import anchor missing")
    text=text.replace(anchor,anchor+imp,1)

get_method='    def do_GET(self):\n'
get_route="""    def do_GET(self):
        if self.path.split("?",1)[0]=="/api/four-channel-production/status":
            self.send_json(four_channel_production_status(ROOT)); return
"""
if '/api/four-channel-production/status' not in text:
    if get_method not in text:
        raise RuntimeError("v1.14 do_GET anchor missing")
    text=text.replace(get_method,get_route,1)

post_method='    def do_POST(self):\n'
post_route="""    def do_POST(self):
        if self.path.split("?",1)[0]=="/api/four-channel-production/run":
            try:
                _body=self.read_body()
                self.send_json(run_four_channel_production_qa(ROOT),200); return
            except Exception as e:
                self.send_json({"ok":False,"error":"4-Channel Production QA failed: "+str(e)},400); return
"""
if '/api/four-channel-production/run' not in text:
    if post_method not in text:
        raise RuntimeError("v1.14 do_POST anchor missing")
    text=text.replace(post_method,post_route,1)

text=text.replace('<div class="ver">v1.13.0</div>','<div class="ver">v1.14.0</div>')
runtime=ROOT/"factory"/"state"/"control_center_v114_runtime.py"
runtime.parent.mkdir(parents=True,exist_ok=True)
runtime.write_text(text,encoding="utf-8")
runpy.run_path(str(runtime),run_name="__main__")
'''

if not SRC.exists():
    raise SystemExit("missing source package: "+str(SRC))

with zipfile.ZipFile(SRC,"r") as zin:
    entries={n:zin.read(n) for n in zin.namelist()}

entries["payload/control_center_v114_bootstrap.py"]=BOOTSTRAP.encode("utf-8")
manifest=json.loads(entries["update_manifest.json"])
manifest["package_id"]="LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_0_R3"
for f in manifest["files"]:
    if f["source"]=="payload/control_center_v114_bootstrap.py":
        f["sha256"]=sha_bytes(entries[f["source"]])
entries["update_manifest.json"]=(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n").encode("utf-8")

notes=entries.get("release_notes.md",b"").decode("utf-8")
notes+="\n\nR3: Fixes bootstrap startup by resolving the QA module path explicitly and injecting Production QA routes at do_GET/do_POST boundaries without depending on the removed local-upload route.\n"
entries["release_notes.md"]=notes.encode("utf-8")

with tempfile.TemporaryDirectory() as td:
    p=Path(td)/"bootstrap.py"; p.write_text(BOOTSTRAP,encoding="utf-8"); py_compile.compile(str(p),doraise=True)

with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as zout:
    for name,data in entries.items():
        zout.writestr(name,data)

with zipfile.ZipFile(OUT,"r") as z:
    m=json.loads(z.read("update_manifest.json"))
    for f in m["files"]:
        actual=sha_bytes(z.read(f["source"]))
        if actual!=f["sha256"]:
            raise SystemExit("payload SHA mismatch: "+f["source"])

digest=sha_file(OUT)
stamp=datetime.now(timezone.utc)
feed={
  "schema":"LONGFORM_FACTORY_UPDATE_FEED_v1",
  "generated_at":stamp.isoformat(),
  "channels":{"dev":{
    "version":"1.14.0",
    "package_url":"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_0_r3.lfupdate.zip",
    "package_sha256":digest,
    "updater_api_min":"1.1",
    "published_at":stamp.isoformat(),
    "title":"Four-Channel Production Integration · R3",
    "summary":"Fixes the v1.14 bootstrap startup path and integrates the four-channel production QA."
  }},
  "cache_bust":"1.14.0-r3-"+stamp.strftime("%Y%m%dT%H%M%S%fZ")
}
(ROOT/"feed.json").write_text(json.dumps(feed,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"package":str(OUT),"bytes":OUT.stat().st_size,"sha256":digest},indent=2))

# trigger publish workflow
