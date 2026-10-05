from pathlib import Path
import hashlib,json,zipfile,py_compile,tempfile
SRC=Path("packages/LONGFORM_FACTORY_GREENLIGHT_EPISODE_TARGET_FIX_1_14_14.lfupdate.zip")
OUT=Path("packages/LONGFORM_FACTORY_GREENLIGHT_PANEL_TARGET_FIX_1_14_15.lfupdate.zip")
def sha(b): return hashlib.sha256(b).hexdigest()
with zipfile.ZipFile(SRC) as z: files={n:z.read(n) for n in z.namelist()}
boot="payload/control_center_v114_bootstrap.py"
bt=files[boot].decode()
bt=bt.replace('FACTORY_VERSION="1.14.14"','FACTORY_VERSION="1.14.15"').replace('<div class="ver">v1.14.14</div>','<div class="ver">v1.14.15</div>')
old='var p=o.parentElement;while(p&&p!==document.body&&p.innerText.indexOf("Greenlight Review")<0)p=p.parentElement;if(!p||p===document.body)return;var ids=(p.innerText.match(/JP_BTS_EP\\d+/g)||[]).filter(function(v,i,a){return a.indexOf(v)===i});if(ids.length!==1)return;var m=[ids[0]];'
new='var p=o.parentElement,ids=[];while(p&&p!==document.body){ids=(p.innerText.match(/JP_BTS_EP\\d+/g)||[]).filter(function(v,i,a){return a.indexOf(v)===i});if(p.innerText.indexOf("Greenlight Review")>=0&&ids.length===1)break;p=p.parentElement}if(!p||p===document.body||ids.length!==1)return;var m=[ids[0]];'
if old not in bt: raise RuntimeError("v1.14.14 panel selector anchor missing")
bt=bt.replace(old,new,1)
files[boot]=bt.encode()
m=json.loads(files["update_manifest.json"])
m.update(package_id="LONGFORM_FACTORY_GREENLIGHT_PANEL_TARGET_FIX_1_14_15",version="1.14.15",from_versions=["1.14.14"],title="Greenlight Panel Target Fix",summary="Finds the selected Greenlight panel only when both its review heading and one unique JP_BTS episode ID are present.")
for f in m["files"]:
    if f["source"] in files:f["sha256"]=sha(files[f["source"]])
files["update_manifest.json"]=(json.dumps(m,ensure_ascii=False,indent=2)+"\n").encode()
with tempfile.TemporaryDirectory() as td:
    p=Path(td)/"control_center_v114_bootstrap.py";p.write_bytes(files[boot]);py_compile.compile(str(p),doraise=True)
assert "setInterval(f,500)" not in bt and "MutationObserver" in bt
assert 'p.innerText.indexOf("Greenlight Review")>=0&&ids.length===1' in bt
assert 'p===document.body||ids.length!==1' in bt
with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
    for n,v in files.items():z.writestr(n,v)
with zipfile.ZipFile(OUT) as z:
    assert z.testzip() is None
    mm=json.loads(z.read("update_manifest.json"));assert mm["version"]=="1.14.15" and mm["from_versions"]==["1.14.14"]
    for f in mm["files"]:assert sha(z.read(f["source"]))==f["sha256"]
digest=sha(OUT.read_bytes())
feed={"schema":"LONGFORM_FACTORY_UPDATE_FEED_v1","generated_at":"AUTO","channels":{"dev":{"version":"1.14.15","package_url":"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/LONGFORM_FACTORY_GREENLIGHT_PANEL_TARGET_FIX_1_14_15.lfupdate.zip","package_sha256":digest,"updater_api_min":"1.1","published_at":"AUTO","title":"Greenlight Panel Target Fix","summary":"Safely resolves the selected Greenlight panel and restores its review actions."}},"cache_bust":"1.14.15-auto"}
Path("feed.v11415.json").write_text(json.dumps(feed,indent=2)+"\n")
Path("staging/v1.14.15/package_sha256.txt").parent.mkdir(parents=True,exist_ok=True)
Path("staging/v1.14.15/package_sha256.txt").write_text(digest+"\n")
print(digest)
