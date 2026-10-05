from pathlib import Path
import hashlib,json,zipfile,py_compile,tempfile,sys,importlib
SRC=Path("packages/LONGFORM_FACTORY_GREENLIGHT_ADAPTER_FIX_1_14_19.lfupdate.zip")
OUT=Path("packages/LONGFORM_FACTORY_GREENLIGHT_CONTRACT_FIX_1_14_20.lfupdate.zip")
def sha(b): return hashlib.sha256(b).hexdigest()
with zipfile.ZipFile(SRC) as z: files={n:z.read(n) for n in z.namelist()}
ap="payload/adapters/channels/jp_bts/production_adapter_v11.py"
s=files[ap].decode()
start=s.index("    def review_greenlight(self, episode_id, decision, note=\"\"):")
# review_greenlight was appended at class tail in v1.14.11; replace the whole tail with contract-based implementation.
s=s[:start]+'''    def review_greenlight(self, episode_id, decision, note=""):
        ep=self.root/"projects"/self.CHANNEL_ID/"episodes"/episode_id
        manifest_path=ep/"episode_manifest.json"
        if not manifest_path.exists():
            raise RuntimeError("Episode manifest not found: "+str(manifest_path))
        m=json.loads(manifest_path.read_text(encoding="utf-8"))
        if self._stage(m)!="GREENLIGHT" or self._stage_state(m)!="NEEDS_REVIEW":
            raise RuntimeError("GREENLIGHT is not awaiting review")
        decision=str(decision or "").upper()
        if decision not in {"APPROVE","HOLD","REJECT"}:
            raise ValueError("invalid Greenlight decision")
        d=self._disc(m); winner=d.get("winner_candidate_id")
        if decision=="APPROVE" and (d.get("status")!="DISCOVERY_PASS" or not winner):
            raise RuntimeError("Cannot approve without clean Discovery winner")
        m["greenlight_review"]={"decision":decision,"note":str(note or ""),"winner_candidate_id":winner,"discovery_gate_status":d.get("status")}
        if decision=="APPROVE":
            out=self._greenlight(ep,m,{"decision":"GREENLIGHT"})
        elif decision=="REJECT":
            out=self._greenlight(ep,m,{"decision":"DROP"})
        else:
            self._set_stage(m,"GREENLIGHT","NEEDS_REVIEW",current=True)
            self._save_manifest(ep,m)
            out={"ok":True,"message":"Greenlight decision: HOLD"}
        return {"ok":True,"decision":decision,"winner_candidate_id":winner,"current_stage":self._stage(m),"current_state":self._stage_state(m),"message":out.get("message","")}
'''
files[ap]=s.encode()
boot="payload/control_center_v114_bootstrap.py"
bt=files[boot].decode().replace('FACTORY_VERSION="1.14.19"','FACTORY_VERSION="1.14.20"').replace('<div class="ver">v1.14.19</div>','<div class="ver">v1.14.20</div>')
assert "UpdateManager feed fetch callsite anchor missing" not in bt
files[boot]=bt.encode()
m=json.loads(files["update_manifest.json"])
m.update(package_id="LONGFORM_FACTORY_GREENLIGHT_CONTRACT_FIX_1_14_20",version="1.14.20",from_versions=["1.14.19"],title="Greenlight Contract Fix",summary="Removes duplicated JP_BTS Greenlight lifecycle logic. Discovery-v2 review now validates eligibility then delegates transitions to the existing ProductionLifecycleAdapter._greenlight contract.",server_script="factory/control_center_v114_bootstrap.py")
for x in m["files"]:
 if x["source"] in files:x["sha256"]=sha(files[x["source"]])
files["update_manifest.json"]=(json.dumps(m,ensure_ascii=False,indent=2)+"\n").encode()
with tempfile.TemporaryDirectory() as td:
 td=Path(td)
 for n,v in files.items():
  if n.startswith("payload/"):
   p=td/n[len("payload/"):];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(v)
 for n in (boot,ap):
  p=td/Path(n[len("payload/"):]);py_compile.compile(str(p),doraise=True)
 stub=td/"adapters"/"channels"/"base_capability_adapter.py"
 stub.parent.mkdir(parents=True,exist_ok=True)
 if not stub.exists():
  stub.write_text("""class DeclarativeCapabilityAdapter:
    def __init__(self,root): self.root=root
    def describe(self,context): return {}
    def preflight(self,stage,context): return {"checks":[]}
""",encoding="utf-8")
 sys.path.insert(0,str(td))
 try:
  mod=importlib.import_module("adapters.channels.jp_bts.production_adapter_v11")
  Adapter=mod.JPBTSProductionAdapter
  for decision,expected_stage,expected_state in [("APPROVE","RESEARCH","READY"),("HOLD","GREENLIGHT","NEEDS_REVIEW"),("REJECT","GREENLIGHT","DROPPED")]:
   root=td/("case_"+decision); ep=root/"projects"/"JP_BTS"/"episodes"/"JP_BTS_EPTEST";ep.mkdir(parents=True)
   manifest={"episode_id":"JP_BTS_EPTEST","lifecycle":{"current_stage":"GREENLIGHT","stages":{"GREENLIGHT":{"runtime_state":"NEEDS_REVIEW"}}},"jp_bts_discovery_v2":{"status":"DISCOVERY_PASS","winner_candidate_id":"ETC","history":[]}}
   (ep/"episode_manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
   a=Adapter.__new__(Adapter); a.root=root; out=a.review_greenlight("JP_BTS_EPTEST",decision)
   saved=json.loads((ep/"episode_manifest.json").read_text())
   assert out["current_stage"]==expected_stage,(decision,out)
   assert saved["lifecycle"]["stages"]["GREENLIGHT"]["runtime_state"]==("COMPLETE" if decision=="APPROVE" else ("NEEDS_REVIEW" if decision=="HOLD" else "DROPPED"))
   if decision=="APPROVE": assert saved["lifecycle"]["stages"]["RESEARCH"]["runtime_state"]=="READY"
 finally:
  sys.path.pop(0)
with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
 for n,v in files.items():z.writestr(n,v)
with zipfile.ZipFile(OUT) as z:
 assert z.testzip() is None
 mm=json.loads(z.read("update_manifest.json"));assert mm["version"]=="1.14.20"
 a=z.read(ap).decode()
 for bad in ("self._episode_dir","self._load_manifest","self._state("): assert bad not in a
 assert "self._greenlight(ep,m" in a and "self._stage_state(m)" in a
 for x in mm["files"]:assert sha(z.read(x["source"]))==x["sha256"]
digest=sha(OUT.read_bytes())
feed={"schema":"LONGFORM_FACTORY_UPDATE_FEED_v1","generated_at":"AUTO","channels":{"dev":{"version":"1.14.20","package_url":"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/LONGFORM_FACTORY_GREENLIGHT_CONTRACT_FIX_1_14_20.lfupdate.zip","package_sha256":digest,"updater_api_min":"1.1","published_at":"AUTO","title":"Greenlight Contract Fix","summary":"JP_BTS Discovery-v2 Greenlight review now delegates to the tested base lifecycle contract; APPROVE/HOLD/REJECT fixture tests are mandatory."}},"cache_bust":"1.14.20-auto"}
Path("feed.v11420.json").write_text(json.dumps(feed,indent=2)+"\n")
Path("staging/v1.14.20/package_sha256.txt").parent.mkdir(parents=True,exist_ok=True)
Path("staging/v1.14.20/package_sha256.txt").write_text(digest+"\n")
print(digest)
