from pathlib import Path
import hashlib,json,zipfile,py_compile,tempfile
SRC=Path("packages/LONGFORM_FACTORY_GREENLIGHT_PANEL_TARGET_FIX_1_14_15.lfupdate.zip")
OUT=Path("packages/LONGFORM_FACTORY_UPDATER_CALLSITE_FIX_1_14_16.lfupdate.zip")
def sha(b): return hashlib.sha256(b).hexdigest()
with zipfile.ZipFile(SRC) as z: files={n:z.read(n) for n in z.namelist()}
boot="payload/control_center_v114_bootstrap.py"
bt=files[boot].decode()
bt=bt.replace('FACTORY_VERSION="1.14.15"','FACTORY_VERSION="1.14.16"').replace('<div class="ver">v1.14.15</div>','<div class="ver">v1.14.16</div>')
anchor='runtime=ROOT/"factory"/"state"/"control_center_v114_runtime.py"'
patch=r'''# updater-callsite-freshness-11416
# Root fix: mutate the URL at the UpdateManager check_remote callsite itself.
# This does not depend on urllib monkey-patching/import order.
_lf_old='feed=self._fetch_json(url)'
_lf_new='feed=self._fetch_json(url+("&" if "?" in url else "?")+"_lfcb_runtime="+str(__import__("time").time_ns()))'
if _lf_old in text:
    text=text.replace(_lf_old,_lf_new,1)
elif "_lfcb_runtime=" not in text:
    raise RuntimeError("UpdateManager feed fetch callsite anchor missing")
'''
if anchor not in bt: raise RuntimeError("runtime generation anchor missing")
bt=bt.replace(anchor,patch+"\n"+anchor,1)
files[boot]=bt.encode()
m=json.loads(files["update_manifest.json"])
m.update(package_id="LONGFORM_FACTORY_UPDATER_CALLSITE_FIX_1_14_16",version="1.14.16",from_versions=["1.14.14","1.14.15"],title="Updater Callsite Freshness Fix",summary="Moves feed cache busting into UpdateManager check_remote itself so every update check uses a unique URL independent of urllib import order.")
for f in m["files"]:
    if f["source"] in files:f["sha256"]=sha(files[f["source"]])
files["update_manifest.json"]=(json.dumps(m,ensure_ascii=False,indent=2)+"\n").encode()
with tempfile.TemporaryDirectory() as td:
    p=Path(td)/"control_center_v114_bootstrap.py";p.write_bytes(files[boot]);py_compile.compile(str(p),doraise=True)
assert "_lfcb_runtime=" in bt
assert "feed=self._fetch_json(url)" in bt
assert "setInterval(f,500)" not in bt and "MutationObserver" in bt
with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
    for n,v in files.items():z.writestr(n,v)
with zipfile.ZipFile(OUT) as z:
    assert z.testzip() is None
    mm=json.loads(z.read("update_manifest.json"));assert mm["version"]=="1.14.16"
    assert set(mm["from_versions"])=={"1.14.14","1.14.15"}
    for f in mm["files"]:assert sha(z.read(f["source"]))==f["sha256"]
digest=sha(OUT.read_bytes())
feed={"schema":"LONGFORM_FACTORY_UPDATE_FEED_v1","generated_at":"AUTO","channels":{"dev":{"version":"1.14.16","package_url":"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/LONGFORM_FACTORY_UPDATER_CALLSITE_FIX_1_14_16.lfupdate.zip","package_sha256":digest,"updater_api_min":"1.1","published_at":"AUTO","title":"Updater Callsite Freshness Fix","summary":"Root fix: every UpdateManager remote check now uses a unique feed URL at the callsite, independent of urllib monkey-patch behavior."}},"cache_bust":"1.14.16-auto"}
Path("feed.v11416.json").write_text(json.dumps(feed,indent=2)+"\n")
Path("staging/v1.14.16/package_sha256.txt").parent.mkdir(parents=True,exist_ok=True)
Path("staging/v1.14.16/package_sha256.txt").write_text(digest+"\n")
print(digest)
