from pathlib import Path
import hashlib,json,zipfile,py_compile,tempfile
SRC=Path("packages/LONGFORM_FACTORY_UPDATER_FRESHNESS_GREENLIGHT_1_14_13.lfupdate.zip")
OUT=Path("packages/LONGFORM_FACTORY_GREENLIGHT_EPISODE_TARGET_FIX_1_14_14.lfupdate.zip")
def sha(b): return hashlib.sha256(b).hexdigest()
with zipfile.ZipFile(SRC) as z: files={n:z.read(n) for n in z.namelist()}
boot="payload/control_center_v114_bootstrap.py"
bt=files[boot].decode()
bt=bt.replace('FACTORY_VERSION="1.14.13"','FACTORY_VERSION="1.14.14"').replace('<div class="ver">v1.14.13</div>','<div class="ver">v1.14.14</div>')
old='var m=document.body.innerText.match(/JP_BTS_EP\\d+/);if(!m)return;var o=Array.from(document.querySelectorAll("button")).find(function(e){return e.textContent.trim()==="Open Episode"});if(!o)return;'
new='var o=Array.from(document.querySelectorAll("button")).find(function(e){return e.textContent.trim()==="Open Episode"});if(!o)return;var p=o.parentElement;while(p&&p!==document.body&&p.innerText.indexOf("Greenlight Review")<0)p=p.parentElement;if(!p||p===document.body)return;var ids=(p.innerText.match(/JP_BTS_EP\\d+/g)||[]).filter(function(v,i,a){return a.indexOf(v)===i});if(ids.length!==1)return;var m=[ids[0]];'
if old not in bt: raise RuntimeError("v1.14.13 Greenlight selector anchor missing")
bt=bt.replace(old,new,1)
files[boot]=bt.encode()
m=json.loads(files["update_manifest.json"])
m.update(package_id="LONGFORM_FACTORY_GREENLIGHT_EPISODE_TARGET_FIX_1_14_14",version="1.14.14",from_versions=["1.14.13"],title="Greenlight Episode Target Safety Fix",summary="Binds Greenlight actions to the selected episode panel instead of the first JP_BTS episode text on the page.")
for f in m["files"]:
    if f["source"] in files: f["sha256"]=sha(files[f["source"]])
files["update_manifest.json"]=(json.dumps(m,ensure_ascii=False,indent=2)+"\n").encode()
with tempfile.TemporaryDirectory() as td:
    p=Path(td)/"control_center_v114_bootstrap.py";p.write_bytes(files[boot]);py_compile.compile(str(p),doraise=True)
assert "setInterval(f,500)" not in bt
assert "MutationObserver" in bt
assert 'ids.length!==1' in bt
assert 'document.body.innerText.match(/JP_BTS_EP' not in bt
with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
    for n,v in files.items(): z.writestr(n,v)
with zipfile.ZipFile(OUT) as z:
    assert z.testzip() is None
    mm=json.loads(z.read("update_manifest.json"))
    assert mm["version"]=="1.14.14" and mm["from_versions"]==["1.14.13"]
    for f in mm["files"]: assert sha(z.read(f["source"]))==f["sha256"]
digest=sha(OUT.read_bytes())
feed={"schema":"LONGFORM_FACTORY_UPDATE_FEED_v1","generated_at":"AUTO","channels":{"dev":{"version":"1.14.14","package_url":"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/LONGFORM_FACTORY_GREENLIGHT_EPISODE_TARGET_FIX_1_14_14.lfupdate.zip","package_sha256":digest,"updater_api_min":"1.1","published_at":"AUTO","title":"Greenlight Episode Target Safety Fix","summary":"Binds Greenlight actions to the selected episode panel before approval."}},"cache_bust":"1.14.14-auto"}
Path("feed.v11414.json").write_text(json.dumps(feed,indent=2)+"\n")
Path("staging/v1.14.14/package_sha256.txt").parent.mkdir(parents=True,exist_ok=True)
Path("staging/v1.14.14/package_sha256.txt").write_text(digest+"\n")
print(digest)
