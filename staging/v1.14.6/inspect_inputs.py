from pathlib import Path
import json, zipfile, hashlib

SRC=Path("packages/LONGFORM_FACTORY_FOUR_CHANNEL_PRODUCTION_1_14_5.lfupdate.zip")
OUT=Path("staging/v1.14.6/inspection")
OUT.mkdir(parents=True,exist_ok=True)
if not SRC.exists(): raise SystemExit("missing v1.14.5 package")
wanted=[
 "update_manifest.json",
 "payload/adapters/channels/jp_bts/production_adapter_v10.py",
 "payload/adapters/channels/production_adapter_common_v10.py",
 "payload/reasoning_provider_bridge.py",
 "payload/adapters/adapter_registry.json",
 "payload/canonical/LONGFORM_FACTORY_ADAPTER_REGISTRY_v2_0.json",
 "payload/canonical/LONGFORM_FACTORY_ACTIVE_AUTHORITY_v2_0.json",
 "payload/control_center_v114_bootstrap.py"
]
report={"source":str(SRC),"source_sha256":hashlib.sha256(SRC.read_bytes()).hexdigest(),"entries":[]}
with zipfile.ZipFile(SRC) as z:
    names=set(z.namelist())
    for n in wanted:
        row={"path":n,"present":n in names}
        if n in names:
            data=z.read(n)
            row["bytes"]=len(data); row["sha256"]=hashlib.sha256(data).hexdigest()
            if n.endswith((".py",".json",".md",".txt")):
                dest=OUT/Path(n).name
                dest.write_bytes(data)
                row["snapshot"]=str(dest)
        report["entries"].append(row)
    report["jp_bts_candidates"]=[n for n in sorted(names) if "jp_bts" in n.lower()]
    report["adapter_registry_candidates"]=[n for n in sorted(names) if "adapter_registry" in n.lower()]
(OUT/"REPORT.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(report,ensure_ascii=False,indent=2))
