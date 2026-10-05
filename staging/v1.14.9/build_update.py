from pathlib import Path
import hashlib,json,zipfile,py_compile,tempfile
SRC=Path("packages/LONGFORM_FACTORY_RESULT_INPUT_STABILITY_1_14_8.lfupdate.zip")
OUT=Path("packages/LONGFORM_FACTORY_RESULT_FOCUS_FIX_1_14_9.lfupdate.zip")
def sha(b): return hashlib.sha256(b).hexdigest()
with zipfile.ZipFile(SRC) as z: files={n:z.read(n) for n in z.namelist()}
boot="payload/control_center_v114_bootstrap.py"
bt=files[boot].decode()
bt=bt.replace('FACTORY_VERSION="1.14.8"','FACTORY_VERSION="1.14.9"')
bt=bt.replace('<div class="ver">v1.14.8</div>','<div class="ver">v1.14.9</div>')

anchor='runtime=ROOT/"factory"/"state"/"control_center_v114_runtime.py"'
patch=r'''
# v1.14.9: do not re-render the dashboard while the AI result textarea owns focus.
# This is intentionally a refresh guard, not a DOM reconstruction workaround.
if "lfResultFocusGuard1149" not in text:
    old="async function refresh(){"
    new="async function refresh(){/*lfResultFocusGuard1149*/if(document.activeElement&&document.activeElement.id==='resultbox')return;"
    if old not in text:
        raise RuntimeError("v1.14.9 dashboard refresh anchor missing")
    text=text.replace(old,new,1)
'''
if anchor not in bt: raise SystemExit("runtime anchor missing")
bt=bt.replace(anchor,patch+anchor,1)
files[boot]=bt.encode()

m=json.loads(files["update_manifest.json"])
m["package_id"]="LONGFORM_FACTORY_RESULT_FOCUS_FIX_1_14_9"
m["version"]="1.14.9";m["from_versions"]=["1.14.8"]
m["title"]="AI Result Focus Fix"
m["summary"]="Pauses dashboard auto-refresh only while AI Result JSON owns focus, preserving continuous typing without DOM replacement."
for f in m["files"]:
    if f["source"] in files:f["sha256"]=sha(files[f["source"]])
files["update_manifest.json"]=(json.dumps(m,ensure_ascii=False,indent=2)+"\n").encode()
files["release_notes.md"]=files.get("release_notes.md",b"")+b"\n\n1.14.9: Guard dashboard refresh while #resultbox owns focus.\n"
with tempfile.TemporaryDirectory() as td:
 p=Path(td)/"b.py";p.write_bytes(files[boot]);py_compile.compile(str(p),doraise=True)
with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
 for n,b in files.items():z.writestr(n,b)
with zipfile.ZipFile(OUT) as z:
 assert z.testzip() is None
 mm=json.loads(z.read("update_manifest.json"));assert mm["version"]=="1.14.9"
 for f in mm["files"]:assert sha(z.read(f["source"]))==f["sha256"]
 b=z.read(boot).decode()
 assert "lfResultFocusGuard1149" in b
 assert "document.activeElement.id==='resultbox'" in b
 rr=json.loads(z.read("payload/adapters/adapter_registry.json"))
 assert rr["channels"]["JP_BTS"]["default_adapter"]=="JP_BTS_PRODUCTION_ADAPTER_v1_1"
 assert rr["channels"]["EN_BTS"]["default_adapter"]=="EN_BTS_PRODUCTION_ADAPTER_v1_2"
digest=sha(OUT.read_bytes())
feed={"schema":"LONGFORM_FACTORY_UPDATE_FEED_v1","generated_at":"AUTO","channels":{"dev":{"version":"1.14.9","package_url":"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/LONGFORM_FACTORY_RESULT_FOCUS_FIX_1_14_9.lfupdate.zip","package_sha256":digest,"updater_api_min":"1.1","published_at":"AUTO","title":"AI Result Focus Fix","summary":"Pauses dashboard auto-refresh only while AI Result JSON owns focus, preserving continuous typing without DOM replacement."}},"cache_bust":"1.14.9-auto"}
Path("feed.v1149.json").write_text(json.dumps(feed,ensure_ascii=False,indent=2)+"\n")
print(digest)

# publish trigger
