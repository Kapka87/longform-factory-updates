from pathlib import Path
import json, zipfile, hashlib

SRC=Path("packages/LONGFORM_FACTORY_JP_BTS_DISCOVERY_GATE_V2_1_14_6.lfupdate.zip")
OUT=Path("staging/v1.14.6/inspection_ui")
OUT.mkdir(parents=True,exist_ok=True)
if not SRC.exists(): raise SystemExit("missing v1.14.6 package")
needles=["AI result JSON","Import Result","Paste RESULT.json","result-input","result_json","textarea","setInterval","refreshStatus","loadEpisode","innerHTML"]
report={"source":str(SRC),"source_sha256":hashlib.sha256(SRC.read_bytes()).hexdigest(),"matches":[]}
with zipfile.ZipFile(SRC) as z:
    for n in z.namelist():
        if not n.endswith((".py",".html",".js")): continue
        try: s=z.read(n).decode("utf-8")
        except Exception: continue
        hits=[x for x in needles if x in s]
        if hits:
            dest=OUT/(Path(n).name)
            dest.write_text(s,encoding="utf-8")
            report["matches"].append({"path":n,"hits":hits,"snapshot":str(dest)})
(OUT/"REPORT.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(report,ensure_ascii=False,indent=2))
