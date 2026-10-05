from pathlib import Path
import hashlib,json,zipfile,py_compile,tempfile
SRC=Path("packages/LONGFORM_FACTORY_GREENLIGHT_PANEL_TARGET_FIX_1_14_15.lfupdate.zip")
OUT=Path("packages/LONGFORM_FACTORY_GREENLIGHT_ADAPTER_FIX_1_14_19.lfupdate.zip")
def sha(b): return hashlib.sha256(b).hexdigest()
with zipfile.ZipFile(SRC) as z: files={n:z.read(n) for n in z.namelist()}
ap="payload/adapters/channels/jp_bts/production_adapter_v11.py"
s=files[ap].decode()
old='ep=self._episode_dir(episode_id); m=self._load_manifest(ep)'
new='ep=self.root/"projects"/self.CHANNEL_ID/"episodes"/episode_id; manifest_path=ep/"episode_manifest.json"; m=json.loads(manifest_path.read_text(encoding="utf-8"))'
if old not in s: raise RuntimeError("broken review_greenlight path anchor missing")
s=s.replace(old,new,1)
old2='self._set_stage(m,"GREENLIGHT","COMPLETE"); self._set_stage(m,"EDITORIAL","READY",current=True)'
new2='self._set_stage(m,"GREENLIGHT","COMPLETE",decision="GREENLIGHT"); self._set_stage(m,"RESEARCH","READY",current=True)'
if old2 not in s: raise RuntimeError("noncanonical EDITORIAL transition anchor missing")
s=s.replace(old2,new2,1)
files[ap]=s.encode()
boot="payload/control_center_v114_bootstrap.py"
bt=files[boot].decode().replace('FACTORY_VERSION="1.14.15"','FACTORY_VERSION="1.14.19"').replace('<div class="ver">v1.14.15</div>','<div class="ver">v1.14.19</div>')
assert "UpdateManager feed fetch callsite anchor missing" not in bt
files[boot]=bt.encode()
m=json.loads(files["update_manifest.json"])
m.update(package_id="LONGFORM_FACTORY_GREENLIGHT_ADAPTER_FIX_1_14_19",version="1.14.19",from_versions=["1.14.18"],title="Greenlight Adapter Fix",summary="Fixes JP_BTS Greenlight review to use the real episode manifest path and canonical GREENLIGHT to RESEARCH lifecycle transition.",server_script="factory/control_center_v114_bootstrap.py")
for x in m["files"]:
 if x["source"] in files:x["sha256"]=sha(files[x["source"]])
files["update_manifest.json"]=(json.dumps(m,ensure_ascii=False,indent=2)+"\n").encode()
with tempfile.TemporaryDirectory() as td:
 for n in (boot,ap):
  p=Path(td)/Path(n).name;p.write_bytes(files[n]);py_compile.compile(str(p),doraise=True)
with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
 for n,v in files.items():z.writestr(n,v)
with zipfile.ZipFile(OUT) as z:
 assert z.testzip() is None
 mm=json.loads(z.read("update_manifest.json"));assert mm["version"]=="1.14.19"
 a=z.read(ap).decode(); assert "self._episode_dir" not in a and "self._load_manifest" not in a
 assert 'self._set_stage(m,"RESEARCH","READY",current=True)' in a
 assert 'self._set_stage(m,"GREENLIGHT","COMPLETE",decision="GREENLIGHT")' in a
 for x in mm["files"]:assert sha(z.read(x["source"]))==x["sha256"]
digest=sha(OUT.read_bytes())
feed={"schema":"LONGFORM_FACTORY_UPDATE_FEED_v1","generated_at":"AUTO","channels":{"dev":{"version":"1.14.19","package_url":"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/LONGFORM_FACTORY_GREENLIGHT_ADAPTER_FIX_1_14_19.lfupdate.zip","package_sha256":digest,"updater_api_min":"1.1","published_at":"AUTO","title":"Greenlight Adapter Fix","summary":"Fixes JP_BTS Greenlight review episode-path handling and advances approved episodes to canonical RESEARCH READY."}},"cache_bust":"1.14.19-auto"}
Path("feed.v11419.json").write_text(json.dumps(feed,indent=2)+"\n")
Path("staging/v1.14.19/package_sha256.txt").parent.mkdir(parents=True,exist_ok=True)
Path("staging/v1.14.19/package_sha256.txt").write_text(digest+"\n")
print(digest)
