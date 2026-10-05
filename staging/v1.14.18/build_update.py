from pathlib import Path
import hashlib,json,zipfile,py_compile,tempfile
SRC=Path("packages/LONGFORM_FACTORY_RUNTIME_AUTHORITY_RECOVERY_1_14_17.lfupdate.zip")
OUT=Path("packages/LONGFORM_FACTORY_UPDATER_AUTHORITY_FIX_1_14_18.lfupdate.zip")
def sha(b): return hashlib.sha256(b).hexdigest()
with zipfile.ZipFile(SRC) as z: files={n:z.read(n) for n in z.namelist()}
boot="payload/control_center_v114_bootstrap.py"
manager="payload/shared_core/update_manager.py"
bt=files[boot].decode()
bt=bt.replace('FACTORY_VERSION="1.14.17"','FACTORY_VERSION="1.14.18"').replace('<div class="ver">v1.14.17</div>','<div class="ver">v1.14.18</div>')
bad=r'''# updater-callsite-freshness-11416
# Root fix: mutate the URL at the UpdateManager check_remote callsite itself.
# This does not depend on urllib monkey-patching/import order.
_lf_old='feed=self._fetch_json(url)'
_lf_new='feed=self._fetch_json(url+("&" if "?" in url else "?")+"_lfcb_runtime="+str(__import__("time").time_ns()))'
if _lf_old in text:
    text=text.replace(_lf_old,_lf_new,1)
elif "_lfcb_runtime=" not in text:
    raise RuntimeError("UpdateManager feed fetch callsite anchor missing")
'''
assert bad in bt, "bad runtime patch block missing"
bt=bt.replace(bad+"\n","",1)
assert "UpdateManager feed fetch callsite anchor missing" not in bt
assert "updater-callsite-freshness-11416" not in bt
files[boot]=bt.encode()

um=files[manager].decode()
old='feed=self._fetch_json(url)'
new='feed=self._fetch_json(url+("&" if "?" in url else "?")+"_lfcb_runtime="+str(__import__("time").time_ns()))'
if "_lfcb_runtime=" not in um:
    assert old in um, "UpdateManager callsite missing"
    um=um.replace(old,new,1)
assert "_lfcb_runtime=" in um
files[manager]=um.encode()

m=json.loads(files["update_manifest.json"])
m.update(
 package_id="LONGFORM_FACTORY_UPDATER_AUTHORITY_FIX_1_14_18",
 version="1.14.18",
 from_versions=["1.13.0","1.14.14","1.14.15","1.14.16","1.14.17"],
 title="Updater Authority Fix",
 summary="Root recovery: removes runtime self-modifying updater patching from the bootstrap and moves unique feed URL generation into the UpdateManager module itself.",
 server_script="factory/control_center_v114_bootstrap.py"
)
for f in m["files"]:
    if f["source"] in files: f["sha256"]=sha(files[f["source"]])
files["update_manifest.json"]=(json.dumps(m,ensure_ascii=False,indent=2)+"\n").encode()
with tempfile.TemporaryDirectory() as td:
    p=Path(td)/"control_center_v114_bootstrap.py"; p.write_bytes(files[boot]); py_compile.compile(str(p),doraise=True)
    q=Path(td)/"update_manager.py"; q.write_bytes(files[manager]); py_compile.compile(str(q),doraise=True)
assert "MutationObserver" in bt and "setInterval(f,500)" not in bt
with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
    for n,v in files.items(): z.writestr(n,v)
with zipfile.ZipFile(OUT) as z:
    assert z.testzip() is None
    mm=json.loads(z.read("update_manifest.json"))
    assert mm["version"]=="1.14.18" and mm["server_script"]=="factory/control_center_v114_bootstrap.py"
    assert "1.13.0" in mm["from_versions"]
    assert "UpdateManager feed fetch callsite anchor missing" not in z.read(boot).decode()
    assert "_lfcb_runtime=" in z.read(manager).decode()
    for f in mm["files"]: assert sha(z.read(f["source"]))==f["sha256"]
digest=sha(OUT.read_bytes())
feed={"schema":"LONGFORM_FACTORY_UPDATE_FEED_v1","generated_at":"AUTO","channels":{"dev":{"version":"1.14.18","package_url":"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/LONGFORM_FACTORY_UPDATER_AUTHORITY_FIX_1_14_18.lfupdate.zip","package_sha256":digest,"updater_api_min":"1.1","published_at":"AUTO","title":"Updater Authority Fix","summary":"Root recovery: bootstrap no longer rewrites updater code at runtime; UpdateManager owns fresh-feed URL generation directly."}},"cache_bust":"1.14.18-auto"}
Path("feed.v11418.json").write_text(json.dumps(feed,indent=2)+"\n")
Path("staging/v1.14.18/package_sha256.txt").parent.mkdir(parents=True,exist_ok=True)
Path("staging/v1.14.18/package_sha256.txt").write_text(digest+"\n")
print(digest)
