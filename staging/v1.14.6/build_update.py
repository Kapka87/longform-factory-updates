from pathlib import Path
import hashlib,json,zipfile,py_compile,tempfile

SRC=Path("packages/LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_5.lfupdate.zip")
OUT=Path("packages/LONGFORM_FACTORY_JP_BTS_DISCOVERY_GATE_V2_1_14_6.lfupdate.zip")
ADAPTER_SRC=Path("staging/v1.14.6/production_adapter_v11.py")
def sha(b): return hashlib.sha256(b).hexdigest()
if not SRC.exists(): raise SystemExit("missing v1.14.5 package")
if not ADAPTER_SRC.exists(): raise SystemExit("missing JP_BTS v1.1 source")
with zipfile.ZipFile(SRC,"r") as z: files={n:z.read(n) for n in z.namelist()}

new_adapter="payload/adapters/channels/jp_bts/production_adapter_v11.py"
files[new_adapter]=ADAPTER_SRC.read_bytes()

for regpath in ["payload/adapters/adapter_registry.json","payload/canonical/LONGFORM_FACTORY_ADAPTER_REGISTRY_v2_0.json"]:
    reg=json.loads(files[regpath])
    old=reg["adapters"]["JP_BTS_PRODUCTION_ADAPTER_v1_0"]
    old["status"]="LEGACY_ACTIVE_PRODUCTION"
    reg["adapters"]["JP_BTS_PRODUCTION_ADAPTER_v1_1"]={
      "adapter_id":"JP_BTS_PRODUCTION_ADAPTER_v1_1",
      "module":"adapters.channels.jp_bts.production_adapter_v11",
      "class":"JPBTSProductionAdapter",
      "channel_id":"JP_BTS","profile":"JP_TECH_v1","status":"ACTIVE_PRODUCTION",
      "requires":{"core_contract":">=1.0,<2.0","manifest_schema":">=1.2,<2.0","profile":"JP_TECH_v1"}
    }
    ch=reg["channels"]["JP_BTS"]
    ch["previous_default_adapter"]="JP_BTS_PRODUCTION_ADAPTER_v1_0"
    ch["default_adapter"]="JP_BTS_PRODUCTION_ADAPTER_v1_1"
    files[regpath]=(json.dumps(reg,ensure_ascii=False,indent=2)+"\n").encode()

authpath="payload/canonical/LONGFORM_FACTORY_ACTIVE_AUTHORITY_v2_0.json"
auth=json.loads(files[authpath])
auth["channels"]["JP_BTS"]["adapter"]="JP_BTS_PRODUCTION_ADAPTER_v1_1"
auth["application_policy"]["existing_episode_auto_migration"]="DISABLED"
auth["application_policy"]["jp_bts_discovery_contract"]="JP_BTS_DISCOVERY_GATE_v2"
files[authpath]=(json.dumps(auth,ensure_ascii=False,indent=2)+"\n").encode()

boot="payload/control_center_v114_bootstrap.py"
bt=files[boot].decode()
bt=bt.replace('FACTORY_VERSION="1.14.5"','FACTORY_VERSION="1.14.6"')
bt=bt.replace('<div class="ver">v1.14.5</div>','<div class="ver">v1.14.6</div>')
files[boot]=bt.encode()

m=json.loads(files["update_manifest.json"])
m["package_id"]="LONGFORM_FACTORY_JP_BTS_DISCOVERY_GATE_V2_1_14_6"
m["version"]="1.14.6"; m["from_versions"]=["1.14.5"]
m["title"]="JP_BTS Discovery Gate v2"
m["summary"]="Adds staged D0 Wide, D1 Market Screen and D2 Deep Validation discovery for new JP_BTS production episodes while preserving pinned v1.0 episodes."
sources={f["source"]:f for f in m["files"]}
if new_adapter not in sources:
    m["files"].append({"source":new_adapter,"target":"factory/adapters/channels/jp_bts/production_adapter_v11.py","sha256":"","mode":"0644"})
for f in m["files"]: f["sha256"]=sha(files[f["source"]])
files["update_manifest.json"]=(json.dumps(m,ensure_ascii=False,indent=2)+"\n").encode()
files["release_notes.md"]=files.get("release_notes.md",b"")+b"\n\n1.14.6: JP_BTS Discovery Gate v2 adds D0 Wide -> D1 Market Screen -> D2 Deep Validation. Existing pinned episodes are not auto-migrated.\n"

with tempfile.TemporaryDirectory() as td:
    for n in [new_adapter,boot]:
        p=Path(td)/Path(n).name; p.write_bytes(files[n]); py_compile.compile(str(p),doraise=True)
with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
    for n,b in files.items(): z.writestr(n,b)
with zipfile.ZipFile(OUT) as z:
    assert z.testzip() is None
    mm=json.loads(z.read("update_manifest.json")); assert mm["version"]=="1.14.6"
    for f in mm["files"]: assert sha(z.read(f["source"]))==f["sha256"],f["source"]
    a=z.read(new_adapter).decode()
    assert 'ADAPTER_ID="JP_BTS_PRODUCTION_ADAPTER_v1_1"' in a
    assert 'PHASES=("D0_WIDE","D1_MARKET_SCREEN","D2_DEEP_VALIDATION")' in a
    assert "winner_candidate_id" in a and "Hard Kill overrides" in a
    rr=json.loads(z.read("payload/adapters/adapter_registry.json"))
    assert rr["channels"]["JP_BTS"]["default_adapter"]=="JP_BTS_PRODUCTION_ADAPTER_v1_1"
    assert rr["adapters"]["JP_BTS_PRODUCTION_ADAPTER_v1_0"]["status"]=="LEGACY_ACTIVE_PRODUCTION"
digest=sha(OUT.read_bytes())
feed={"schema":"LONGFORM_FACTORY_UPDATE_FEED_v1","generated_at":"AUTO","channels":{"dev":{"version":"1.14.6","package_url":"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/LONGFORM_FACTORY_JP_BTS_DISCOVERY_GATE_V2_1_14_6.lfupdate.zip","package_sha256":digest,"updater_api_min":"1.1","published_at":"AUTO","title":"JP_BTS Discovery Gate v2","summary":"Adds staged revenue-first D0/D1/D2 discovery for JP_BTS while preserving existing pinned episodes."}},"cache_bust":"1.14.6-auto"}
Path("feed.v1146.json").write_text(json.dumps(feed,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"bytes":OUT.stat().st_size,"sha256":digest},indent=2))
