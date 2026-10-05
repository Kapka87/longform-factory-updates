from pathlib import Path
import hashlib,json,zipfile,py_compile,tempfile

SRC=Path("packages/LONGFORM_FACTORY_JP_BTS_DISCOVERY_GATE_V2_1_14_6.lfupdate.zip")
OUT=Path("packages/LONGFORM_FACTORY_JP_BTS_DISCOVERY_UI_FIX_1_14_7.lfupdate.zip")
def sha(b): return hashlib.sha256(b).hexdigest()
if not SRC.exists(): raise SystemExit("missing v1.14.6 package")
with zipfile.ZipFile(SRC,"r") as z: files={n:z.read(n) for n in z.namelist()}

# 1) Keep current-production integration expectations aligned with JP_BTS v1.1.
for p in ["payload/cross_channel_integration.py","payload/qa/four_channel_production_integration.py"]:
    if p in files:
        s=files[p].decode()
        s=s.replace('"JP_BTS":("JP_TECH_v1","JP_BTS_PRODUCTION_ADAPTER_v1_0")',
                    '"JP_BTS":("JP_TECH_v1","JP_BTS_PRODUCTION_ADAPTER_v1_1")')
        s=s.replace("'JP_BTS':('JP_TECH_v1','JP_BTS_PRODUCTION_ADAPTER_v1_0')",
                    "'JP_BTS':('JP_TECH_v1','JP_BTS_PRODUCTION_ADAPTER_v1_1')")
        files[p]=s.encode()

# 2) Patch generated dashboard runtime: preserve textarea draft across periodic detail re-renders.
boot="payload/control_center_v114_bootstrap.py"
bt=files[boot].decode()
bt=bt.replace('FACTORY_VERSION="1.14.6"','FACTORY_VERSION="1.14.7"')
bt=bt.replace('<div class="ver">v1.14.6</div>','<div class="ver">v1.14.7</div>')
anchor='runtime=ROOT/"factory"/"state"/"control_center_v114_runtime.py"'
patch=r'''
# v1.14.7: the dashboard periodically re-renders episode detail. Preserve a manually
# pasted reasoning result while #resultbox is destroyed/recreated by that refresh.
if "__lfResultDraft" not in text:
    _draft_js = r"""<script>
window.__lfResultDraft = window.__lfResultDraft || "";
document.addEventListener("input", function(ev){
  if(ev.target && ev.target.id==="resultbox"){
    window.__lfResultDraft = ev.target.value || "";
  }
}, true);
document.addEventListener("paste", function(ev){
  if(ev.target && ev.target.id==="resultbox"){
    setTimeout(function(){ window.__lfResultDraft = ev.target.value || ""; },0);
  }
}, true);
new MutationObserver(function(){
  var box=document.getElementById("resultbox");
  if(box && !box.value && window.__lfResultDraft){
    box.value=window.__lfResultDraft;
  }
}).observe(document.documentElement,{childList:true,subtree:true});
</script>"""
    if "</body>" not in text:
        raise RuntimeError("v1.14.7 result-draft patch anchor missing")
    text=text.replace("</body>",_draft_js+"</body>",1)

'''
if patch.strip() not in bt:
    if anchor not in bt: raise SystemExit("bootstrap runtime anchor missing")
    bt=bt.replace(anchor,patch+anchor,1)
files[boot]=bt.encode()

m=json.loads(files["update_manifest.json"])
m["package_id"]="LONGFORM_FACTORY_JP_BTS_DISCOVERY_UI_FIX_1_14_7"
m["version"]="1.14.7"; m["from_versions"]=["1.14.6"]
m["title"]="JP_BTS Discovery Result Input Fix"
m["summary"]="Preserves pasted AI result JSON across dashboard refreshes and aligns JP_BTS production integration expectations with adapter v1.1."
for f in m["files"]:
    if f["source"] in files: f["sha256"]=sha(files[f["source"]])
files["update_manifest.json"]=(json.dumps(m,ensure_ascii=False,indent=2)+"\n").encode()
files["release_notes.md"]=files.get("release_notes.md",b"")+b"\n\n1.14.7: Preserve AI result JSON textarea drafts across dashboard detail refreshes; align JP_BTS integration QA with adapter v1.1.\n"

with tempfile.TemporaryDirectory() as td:
    p=Path(td)/"bootstrap.py"; p.write_bytes(files[boot]); py_compile.compile(str(p),doraise=True)

with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
    for n,b in files.items(): z.writestr(n,b)
with zipfile.ZipFile(OUT) as z:
    assert z.testzip() is None
    mm=json.loads(z.read("update_manifest.json")); assert mm["version"]=="1.14.7"
    for f in mm["files"]: assert sha(z.read(f["source"]))==f["sha256"],f["source"]
    b=z.read(boot).decode()
    assert "__lfResultDraft" in b and 'FACTORY_VERSION="1.14.7"' in b
    rr=json.loads(z.read("payload/adapters/adapter_registry.json"))
    assert rr["channels"]["JP_BTS"]["default_adapter"]=="JP_BTS_PRODUCTION_ADAPTER_v1_1"
    assert rr["channels"]["EN_BTS"]["default_adapter"]=="EN_BTS_PRODUCTION_ADAPTER_v1_2"
    if "payload/cross_channel_integration.py" in z.namelist():
        c=z.read("payload/cross_channel_integration.py").decode()
        assert '"JP_BTS":("JP_TECH_v1","JP_BTS_PRODUCTION_ADAPTER_v1_1")' in c
    if "payload/qa/four_channel_production_integration.py" in z.namelist():
        q=z.read("payload/qa/four_channel_production_integration.py").decode()
        assert '"JP_BTS":("JP_TECH_v1","JP_BTS_PRODUCTION_ADAPTER_v1_1")' in q

digest=sha(OUT.read_bytes())
feed={"schema":"LONGFORM_FACTORY_UPDATE_FEED_v1","generated_at":"AUTO","channels":{"dev":{"version":"1.14.7","package_url":"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/LONGFORM_FACTORY_JP_BTS_DISCOVERY_UI_FIX_1_14_7.lfupdate.zip","package_sha256":digest,"updater_api_min":"1.1","published_at":"AUTO","title":"JP_BTS Discovery Result Input Fix","summary":"Preserves pasted AI result JSON across dashboard refreshes and aligns JP_BTS integration QA with adapter v1.1."}},"cache_bust":"1.14.7-auto"}
Path("feed.v1147.json").write_text(json.dumps(feed,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"bytes":OUT.stat().st_size,"sha256":digest},indent=2))

# publish trigger
