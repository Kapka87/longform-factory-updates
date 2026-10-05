from pathlib import Path
import hashlib,json,zipfile,py_compile,tempfile
SRC=Path("packages/LONGFORM_FACTORY_RESULT_FOCUS_FIX_1_14_9.lfupdate.zip")
OUT=Path("packages/LONGFORM_FACTORY_UPDATER_FRESHNESS_GREENLIGHT_1_14_13.lfupdate.zip")
def sha(b): return hashlib.sha256(b).hexdigest()
with zipfile.ZipFile(SRC) as z: files={n:z.read(n) for n in z.namelist()}
ap="payload/adapters/channels/jp_bts/production_adapter_v11.py"
s=files[ap].decode()
if "def review_greenlight(" not in s:
 s+=r'''
    def review_greenlight(self, episode_id, decision, note=""):
        ep=self._episode_dir(episode_id); m=self._load_manifest(ep)
        if self._stage(m)!="GREENLIGHT" or self._state(m)!="NEEDS_REVIEW": raise RuntimeError("GREENLIGHT is not awaiting review")
        decision=str(decision or "").upper()
        if decision not in {"APPROVE","HOLD","REJECT"}: raise ValueError("invalid Greenlight decision")
        d=self._disc(m); winner=d.get("winner_candidate_id")
        if decision=="APPROVE":
            if d.get("status")!="DISCOVERY_PASS" or not winner: raise RuntimeError("Cannot approve without clean Discovery winner")
            self._set_stage(m,"GREENLIGHT","COMPLETE"); self._set_stage(m,"EDITORIAL","READY",current=True)
        elif decision=="HOLD": self._set_stage(m,"GREENLIGHT","NEEDS_REVIEW",current=True)
        else: self._set_stage(m,"GREENLIGHT","REJECTED",current=True)
        m["greenlight_review"]={"decision":decision,"note":str(note or ""),"winner_candidate_id":winner,"discovery_gate_status":d.get("status")}
        self._save_manifest(ep,m)
        return {"ok":True,"decision":decision,"winner_candidate_id":winner,"current_stage":self._stage(m),"current_state":self._state(m)}
'''
files[ap]=s.encode()
# v1.14.13: make feed freshness deterministic in the installed cache-bust module.
cb="payload/shared_core/update_cache_bust.py"
with zipfile.ZipFile("packages/LONGFORM_FACTORY_LAUNCHER_UPDATER_HARDENING_1_13_0.lfupdate.zip") as _hz:
    u=_hz.read(cb).decode()
# Avoid double mutation: patch urlopen only. The original urlopen then uses the normal opener.
u=u.replace("    urllib.request.OpenerDirector.open=_patched_opener_open\\n","")
files[cb]=u.encode()
boot="payload/control_center_v114_bootstrap.py"; bt=files[boot].decode()
bt=bt.replace('FACTORY_VERSION="1.14.9"','FACTORY_VERSION="1.14.13"').replace('<div class="ver">v1.14.9</div>','<div class="ver">v1.14.13</div>')
anchor='runtime=ROOT/"factory"/"state"/"control_center_v114_runtime.py"'
patch=r'''# greenlight-review-11411
_gl_post='    def do_POST(self):\n'
_gl_route="""    def do_POST(self):
        if self.path.split("?",1)[0].startswith("/api/episodes/") and self.path.split("?",1)[0].endswith("/greenlight-review"):
            try:
                import json as _json
                body=self.read_body()
                if not isinstance(body,dict): body=_json.loads(body.decode("utf-8") if isinstance(body,(bytes,bytearray)) else (body or "{}"))
                episode_id=self.path.split("?",1)[0].split("/")[3]
                from adapters.channels.jp_bts.production_adapter_v11 import JPBTSProductionAdapter
                out=JPBTSProductionAdapter(ROOT).review_greenlight(episode_id,body.get("decision"),body.get("note",""))
                self.send_json(out,200); return
            except Exception as e:
                self.send_json({"ok":False,"error":str(e)},400); return
"""
if "/greenlight-review" not in text:
    if _gl_post not in text: raise RuntimeError("Greenlight do_POST anchor missing")
    text=text.replace(_gl_post,_gl_route,1)
_gl_ui=r"""<script id="greenlight-review-11411">(function(){function f(){if(document.getElementById("greenlight-actions-11411")||!document.body||document.body.innerText.indexOf("Greenlight Review")<0)return;var m=document.body.innerText.match(/JP_BTS_EP\d+/);if(!m)return;var o=Array.from(document.querySelectorAll("button")).find(function(e){return e.textContent.trim()==="Open Episode"});if(!o)return;var x=document.createElement("div");x.id="greenlight-actions-11411";x.style.margin="10px 0";[["APPROVE","Approve Greenlight"],["HOLD","Hold"],["REJECT","Reject"]].forEach(function(v){var b=document.createElement("button");b.textContent=v[1];b.style.marginRight="8px";b.onclick=async function(){var r=await fetch("/api/episodes/"+m[0]+"/greenlight-review",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({decision:v[0]})});var j=await r.json();if(!r.ok||j.ok===false){alert(j.error||"Greenlight review failed");return}location.reload()};x.appendChild(b)});o.parentNode.insertBefore(x,o.nextSibling)}var mo=new MutationObserver(function(){if(!document.getElementById("greenlight-actions-11411"))f()});mo.observe(document.body,{childList:true,subtree:true});f()})();</script>"""
if "greenlight-review-11411" not in text:
    if "</body>" not in text: raise RuntimeError("Greenlight body anchor missing")
    text=text.replace("</body>",_gl_ui+"</body>",1)
'''
if anchor not in bt: raise RuntimeError("runtime anchor missing")
bt=bt.replace(anchor,patch+"\n"+anchor,1); files[boot]=bt.encode()
m=json.loads(files["update_manifest.json"]);m.update(package_id="LONGFORM_FACTORY_UPDATER_FRESHNESS_GREENLIGHT_1_14_13",version="1.14.13",from_versions=["1.14.11"],title="Updater Freshness + Greenlight Stable UI",summary="Makes remote feed freshness intrinsic to UpdateManager and keeps Greenlight actions stable without polling.")
# Ensure repaired cache-bust module is installed by this delta.
if not any(f.get("source")==cb for f in m["files"]):
 m["files"].append({"source":cb,"target":"factory/shared_core/update_cache_bust.py","sha256":sha(files[cb]),"mode":"0644"})
for f in m["files"]:
 if f["source"] in files:f["sha256"]=sha(files[f["source"]])
files["update_manifest.json"]=(json.dumps(m,ensure_ascii=False,indent=2)+"\n").encode()
with tempfile.TemporaryDirectory() as td:
 for n in [boot,ap,cb]:
  p=Path(td)/Path(n).name;p.write_bytes(files[n]);py_compile.compile(str(p),doraise=True)
assert "greenlight-review-11410" not in files[boot].decode()
assert "self.read_body()" in files[boot].decode() and "self.send_json(" in files[boot].decode()
assert '"_lfcb"' in files[cb].decode()
assert 'headers["Cache-Control"]="no-cache"' in files[cb].decode()
assert "urllib.request.urlopen=_patched_urlopen" in files[cb].decode()
assert "urllib.request.OpenerDirector.open=_patched_opener_open" not in files[cb].decode()
with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
 for n,v in files.items():z.writestr(n,v)
with zipfile.ZipFile(OUT) as z:
 assert z.testzip() is None
 mm=json.loads(z.read("update_manifest.json"));assert mm["version"]=="1.14.13"
 for f in mm["files"]:assert sha(z.read(f["source"]))==f["sha256"]
digest=sha(OUT.read_bytes())
feed={"schema":"LONGFORM_FACTORY_UPDATE_FEED_v1","generated_at":"AUTO","channels":{"dev":{"version":"1.14.13","package_url":"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/LONGFORM_FACTORY_UPDATER_FRESHNESS_GREENLIGHT_1_14_13.lfupdate.zip","package_sha256":digest,"updater_api_min":"1.1","published_at":"AUTO","title":"Updater Freshness + Greenlight Stable UI","summary":"Makes feed freshness intrinsic to UpdateManager and preserves stable Greenlight actions."}},"cache_bust":"1.14.13-auto"}
Path("feed.v11413.json").write_text(json.dumps(feed,indent=2)+"\n");Path("staging/v1.14.13/package_sha256.txt").write_text(digest+"\n")
assert m["package_id"]=="LONGFORM_FACTORY_UPDATER_FRESHNESS_GREENLIGHT_1_14_13"
assert m["version"]=="1.14.13" and m["from_versions"]==["1.14.11"]
assert feed["channels"]["dev"]["version"]=="1.14.13"
assert feed["channels"]["dev"]["package_url"].endswith(OUT.name)
assert Path("feed.v11413.json").exists()
print(digest)

# publish trigger

# publish trigger

# publish verified v1.14.13
