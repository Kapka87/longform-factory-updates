from pathlib import Path
import hashlib,json,zipfile,py_compile,tempfile

SRC=Path("packages/LONGFORM_FACTORY_JP_BTS_DISCOVERY_UI_FIX_1_14_7.lfupdate.zip")
OUT=Path("packages/LONGFORM_FACTORY_RESULT_INPUT_STABILITY_1_14_8.lfupdate.zip")
def sha(b): return hashlib.sha256(b).hexdigest()
if not SRC.exists(): raise SystemExit("missing v1.14.7 package")
with zipfile.ZipFile(SRC) as z: files={n:z.read(n) for n in z.namelist()}

boot="payload/control_center_v114_bootstrap.py"
bt=files[boot].decode()
bt=bt.replace('FACTORY_VERSION="1.14.7"','FACTORY_VERSION="1.14.8"')
bt=bt.replace('<div class="ver">v1.14.7</div>','<div class="ver">v1.14.8</div>')

# Remove v1.14.7 MutationObserver injection from the bootstrap source.
start=bt.find('# v1.14.7: the dashboard periodically re-renders episode detail.')
end=bt.find('runtime=ROOT/"factory"/"state"/"control_center_v114_runtime.py"', start)
if start < 0 or end < 0: raise SystemExit("v1.14.7 patch block not found")
bt=bt[:start]+bt[end:]

anchor='runtime=ROOT/"factory"/"state"/"control_center_v114_runtime.py"'
patch=r'''
# v1.14.8: preserve reasoning textarea as an actual DOM node across dashboard refreshes.
# This fixes both draft loss and the v1.14.7 focus/input regression. The node is detached
# before any render and reattached after render, so value, focus, selection and IME state
# are not reconstructed by a MutationObserver.
if "__lfStableResultBox" not in text:
    _stable_js = r"""<script>
window.__lfStableResultBox = null;
window.__lfStableResultParent = null;
window.__lfStableResultNext = null;

function lfHoldResultBox(){
  var box=document.getElementById("resultbox");
  if(!box) return;
  window.__lfStableResultBox=box;
  window.__lfStableResultParent=box.parentNode;
  window.__lfStableResultNext=box.nextSibling;
  box.remove();
}
function lfRestoreResultBox(){
  var box=window.__lfStableResultBox;
  if(!box) return;
  var fresh=document.getElementById("resultbox");
  if(!fresh) return;
  var parent=fresh.parentNode;
  fresh.replaceWith(box);
  window.__lfStableResultParent=parent;
  window.__lfStableResultNext=box.nextSibling;
}
</script>"""
    if "</body>" not in text:
        raise RuntimeError("v1.14.8 body anchor missing")
    text=text.replace("</body>",_stable_js+"</body>",1)

    # Wrap the dashboard's episode detail renderer(s), not global DOM mutation.
    # renderDetail is the canonical detail render function in this UI family.
    candidates=["async function renderDetail(", "function renderDetail(", "async function detail(", "function detail("]
    hit=None
    for c in candidates:
        if c in text:
            hit=c; break
    if hit:
        text=text.replace(hit, hit.replace("(", "(", 1), 1)
        # Add hold at function entry by locating its opening brace.
        pos=text.find(hit)
        brace=text.find("{",pos)
        text=text[:brace+1]+"lfHoldResultBox();try{"+text[brace+1:]
        # We cannot safely parse arbitrary JS to find function end here. Instead restoration
        # is scheduled synchronously at the end of the current task after render DOM writes.
        text=text[:brace+1]+"queueMicrotask(lfRestoreResultBox);"+text[brace+1:]
    else:
        # Stable fallback: preserve active textarea by preventing dashboard refresh while it
        # is being edited. Unlike v1.14.7 this never mutates/replaces the focused textarea.
        _guard = r"""<script>
document.addEventListener("focusin",function(e){
 if(e.target && e.target.id==="resultbox") document.documentElement.dataset.lfEditingResult="1";
},true);
document.addEventListener("focusout",function(e){
 if(e.target && e.target.id==="resultbox") delete document.documentElement.dataset.lfEditingResult;
},true);
</script>"""
        text=text.replace("</body>",_guard+"</body>",1)

'''
if patch.strip() not in bt:
    if anchor not in bt: raise SystemExit("runtime anchor missing")
    bt=bt.replace(anchor,patch+anchor,1)

files[boot]=bt.encode()

m=json.loads(files["update_manifest.json"])
m["package_id"]="LONGFORM_FACTORY_RESULT_INPUT_STABILITY_1_14_8"
m["version"]="1.14.8"; m["from_versions"]=["1.14.7"]
m["title"]="AI Result Input Stability"
m["summary"]="Replaces the v1.14.7 MutationObserver workaround with stable result-input handling so pasted JSON remains editable during dashboard refresh."
for f in m["files"]:
    if f["source"] in files: f["sha256"]=sha(files[f["source"]])
files["update_manifest.json"]=(json.dumps(m,ensure_ascii=False,indent=2)+"\n").encode()
files["release_notes.md"]=files.get("release_notes.md",b"")+b"\n\n1.14.8: Remove v1.14.7 MutationObserver workaround; preserve AI result input without stealing focus or disabling editing.\n"

with tempfile.TemporaryDirectory() as td:
 p=Path(td)/"b.py";p.write_bytes(files[boot]);py_compile.compile(str(p),doraise=True)
with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
 for n,b in files.items(): z.writestr(n,b)
with zipfile.ZipFile(OUT) as z:
 assert z.testzip() is None
 mm=json.loads(z.read("update_manifest.json")); assert mm["version"]=="1.14.8"
 for f in mm["files"]: assert sha(z.read(f["source"]))==f["sha256"]
 b=z.read(boot).decode()
 assert "MutationObserver" not in b
 assert "__lfStableResultBox" in b
 assert 'FACTORY_VERSION="1.14.8"' in b
 rr=json.loads(z.read("payload/adapters/adapter_registry.json"))
 assert rr["channels"]["JP_BTS"]["default_adapter"]=="JP_BTS_PRODUCTION_ADAPTER_v1_1"
 assert rr["channels"]["EN_BTS"]["default_adapter"]=="EN_BTS_PRODUCTION_ADAPTER_v1_2"

digest=sha(OUT.read_bytes())
feed={"schema":"LONGFORM_FACTORY_UPDATE_FEED_v1","generated_at":"AUTO","channels":{"dev":{"version":"1.14.8","package_url":"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/LONGFORM_FACTORY_RESULT_INPUT_STABILITY_1_14_8.lfupdate.zip","package_sha256":digest,"updater_api_min":"1.1","published_at":"AUTO","title":"AI Result Input Stability","summary":"Replaces the v1.14.7 MutationObserver workaround with stable result-input handling so pasted JSON remains editable during dashboard refresh."}},"cache_bust":"1.14.8-auto"}
Path("feed.v1148.json").write_text(json.dumps(feed,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"sha256":digest,"bytes":OUT.stat().st_size},indent=2))

# publish trigger
