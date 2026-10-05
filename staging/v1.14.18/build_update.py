from pathlib import Path
import hashlib,json,zipfile,py_compile,tempfile
SRC=Path("packages/LONGFORM_FACTORY_GREENLIGHT_PANEL_TARGET_FIX_1_14_15.lfupdate.zip")
OUT=Path("packages/LONGFORM_FACTORY_STABLE_RECOVERY_1_14_18.lfupdate.zip")
def sha(b): return hashlib.sha256(b).hexdigest()
with zipfile.ZipFile(SRC) as z: files={n:z.read(n) for n in z.namelist()}
boot="payload/control_center_v114_bootstrap.py"
bt=files[boot].decode()
bt=bt.replace('FACTORY_VERSION="1.14.15"','FACTORY_VERSION="1.14.18"').replace('<div class="ver">v1.14.15</div>','<div class="ver">v1.14.18</div>')
assert "UpdateManager feed fetch callsite anchor missing" not in bt
assert "_lfcb_runtime=" not in bt
assert "MutationObserver" in bt and "setInterval(f,500)" not in bt
files[boot]=bt.encode()
m=json.loads(files["update_manifest.json"])
m.update(package_id="LONGFORM_FACTORY_STABLE_RECOVERY_1_14_18",version="1.14.18",from_versions=["1.13.0","1.14.14","1.14.15","1.14.16","1.14.17"],title="Stable Recovery",summary="Recovery branched directly from the last bootable v1.14.15 line. Excludes the failing v1.14.16 runtime source-rewrite anchor while preserving Greenlight panel targeting and the proven updater cache-bust module.",server_script="factory/control_center_v114_bootstrap.py")
for x in m["files"]:
    if x["source"] in files:x["sha256"]=sha(files[x["source"]])
files["update_manifest.json"]=(json.dumps(m,ensure_ascii=False,indent=2)+"\n").encode()
with tempfile.TemporaryDirectory() as td:
 p=Path(td)/"control_center_v114_bootstrap.py";p.write_bytes(files[boot]);py_compile.compile(str(p),doraise=True)
with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
 for n,v in files.items():z.writestr(n,v)
with zipfile.ZipFile(OUT) as z:
 assert z.testzip() is None
 mm=json.loads(z.read("update_manifest.json"))
 assert mm["version"]=="1.14.18" and mm["server_script"]=="factory/control_center_v114_bootstrap.py"
 assert {"1.13.0","1.14.14"}.issubset(set(mm["from_versions"]))
 bb=z.read(boot).decode()
 assert "UpdateManager feed fetch callsite anchor missing" not in bb and "_lfcb_runtime=" not in bb
 for x in mm["files"]:assert sha(z.read(x["source"]))==x["sha256"]
digest=sha(OUT.read_bytes())
feed={"schema":"LONGFORM_FACTORY_UPDATE_FEED_v1","generated_at":"AUTO","channels":{"dev":{"version":"1.14.18","package_url":"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/LONGFORM_FACTORY_STABLE_RECOVERY_1_14_18.lfupdate.zip","package_sha256":digest,"updater_api_min":"1.1","published_at":"AUTO","title":"Stable Recovery","summary":"Recovery from the last bootable v1.14.15 line; excludes the failing runtime source-rewrite anchor introduced in v1.14.16."}},"cache_bust":"1.14.18-auto"}
Path("feed.v11418.json").write_text(json.dumps(feed,indent=2)+"\n")
Path("staging/v1.14.18/package_sha256.txt").parent.mkdir(parents=True,exist_ok=True)
Path("staging/v1.14.18/package_sha256.txt").write_text(digest+"\n")
print(digest)
