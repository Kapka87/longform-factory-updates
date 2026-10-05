from pathlib import Path
import hashlib,json,zipfile,py_compile,tempfile
SRC=Path("packages/LONGFORM_FACTORY_UPDATER_CALLSITE_FIX_1_14_16.lfupdate.zip")
OUT=Path("packages/LONGFORM_FACTORY_RUNTIME_AUTHORITY_RECOVERY_1_14_17.lfupdate.zip")
def sha(b): return hashlib.sha256(b).hexdigest()
with zipfile.ZipFile(SRC) as z: files={n:z.read(n) for n in z.namelist()}
boot="payload/control_center_v114_bootstrap.py"
bt=files[boot].decode()
bt=bt.replace('FACTORY_VERSION="1.14.16"','FACTORY_VERSION="1.14.17"').replace('<div class="ver">v1.14.16</div>','<div class="ver">v1.14.17</div>')
files[boot]=bt.encode()
m=json.loads(files["update_manifest.json"])
m.update(
 package_id="LONGFORM_FACTORY_RUNTIME_AUTHORITY_RECOVERY_1_14_17",
 version="1.14.17",
 from_versions=["1.13.0","1.14.14","1.14.15","1.14.16"],
 title="Runtime Authority Recovery",
 summary="Recovery release that unifies the updater post-install server/health authority with the v1.14 bootstrap runtime and preserves direct callsite feed freshness.",
 server_script="factory/control_center_v114_bootstrap.py"
)
for f in m["files"]:
    if f["source"] in files:f["sha256"]=sha(files[f["source"]])
files["update_manifest.json"]=(json.dumps(m,ensure_ascii=False,indent=2)+"\n").encode()
with tempfile.TemporaryDirectory() as td:
 p=Path(td)/"control_center_v114_bootstrap.py";p.write_bytes(files[boot]);py_compile.compile(str(p),doraise=True)
assert "_lfcb_runtime=" in bt
assert "MutationObserver" in bt and "setInterval(f,500)" not in bt
assert m["server_script"]=="factory/control_center_v114_bootstrap.py"
assert "1.13.0" in m["from_versions"]
with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
 for n,v in files.items():z.writestr(n,v)
with zipfile.ZipFile(OUT) as z:
 assert z.testzip() is None
 mm=json.loads(z.read("update_manifest.json"))
 assert mm["version"]=="1.14.17"
 assert mm["server_script"]=="factory/control_center_v114_bootstrap.py"
 assert "1.13.0" in mm["from_versions"]
 for f in mm["files"]:assert sha(z.read(f["source"]))==f["sha256"]
digest=sha(OUT.read_bytes())
feed={"schema":"LONGFORM_FACTORY_UPDATE_FEED_v1","generated_at":"AUTO","channels":{"dev":{"version":"1.14.17","package_url":"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/LONGFORM_FACTORY_RUNTIME_AUTHORITY_RECOVERY_1_14_17.lfupdate.zip","package_sha256":digest,"updater_api_min":"1.1","published_at":"AUTO","title":"Runtime Authority Recovery","summary":"Recovery release: updater post-install health now launches the same v1.14 bootstrap runtime used by the app, with direct callsite feed freshness."}},"cache_bust":"1.14.17-auto"}
Path("feed.v11417.json").write_text(json.dumps(feed,indent=2)+"\n")
Path("staging/v1.14.17/package_sha256.txt").parent.mkdir(parents=True,exist_ok=True)
Path("staging/v1.14.17/package_sha256.txt").write_text(digest+"\n")
print(digest)
