from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, re, zipfile, tempfile, shutil, py_compile

ROOT=Path(__file__).resolve().parents[2]
VERSION="1.10.0"
PREV="1.9.9"
PKG_NAME="LONGFORM_FACTORY_CROSS_CHANNEL_FOUNDATION_1_10_0.lfupdate.zip"
PREV_PKG=ROOT/"packages"/"LONGFORM_FACTORY_REMOTE_UI_FIX_1_9_9.lfupdate.zip"
OUT=ROOT/"packages"/PKG_NAME
TMP=Path(tempfile.mkdtemp(prefix="lf1100_"))

def w(rel,text):
    p=TMP/rel
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(text,encoding="utf-8")
    return p

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

BASE_ADAPTER='''from __future__ import annotations
from pathlib import Path

STAGES=["DISCOVERY","GREENLIGHT","RESEARCH","FACT_LOCK","SCRIPT","SCRIPT_QC","VISUAL_PLAN","VISUAL_BUILD","VISUAL_QC","VOICE","TIMING","SUBTITLES","EDIT_PLAN","RENDER","AUTO_QC","PREVIEW_REVIEW","FINAL","THUMBNAIL","TITLE","DESCRIPTION","TAGS","PUBLISHING_QC","PUBLISHING_REVIEW","UPLOAD_READY"]

class DeclarativeCapabilityAdapter:
    ADAPTER_ID=""
    CHANNEL_ID=""
    PROFILE_ID=""
    DISPLAY_NAME=""
    REQUIRED_RULES=[]
    CAPABILITIES={}
    def __init__(self,root:Path): self.root=Path(root)
    def describe(self,context):
        return {"adapter_contract":"1.0","adapter_id":self.ADAPTER_ID,"adapter_version":"1.0","channel_id":self.CHANNEL_ID,"profile_id":self.PROFILE_ID,"display_name":self.DISPLAY_NAME,"integration_status":"ACTIVE_CAPABILITY","media_binding":"PENDING_MEDIA_SMOKE","supported_stages":list(STAGES),"required_rules":list(self.REQUIRED_RULES),"capabilities":self.CAPABILITIES,"requires":{"core_contract":">=1.0,<2.0","manifest_schema":">=1.2,<2.0","profile":self.PROFILE_ID}}
    def inspect(self,ep,manifest):
        return {"active":True,"adapter_id":self.ADAPTER_ID,"stage":manifest.get("lifecycle",{}).get("current_stage","DISCOVERY"),"state":"CAPABILITY_INTEGRATED","buttons":[],"integration_status":"ACTIVE_CAPABILITY","media_binding":"PENDING_MEDIA_SMOKE","message":"Channel capability contract is integrated. Media runner smoke test is still required."}
    def preflight(self,stage,context):
        m=context["manifest"]
        checks=[
          {"name":"Manifest schema","pass":str(m.get("schema_version"))=="1.2","detail":str(m.get("schema_version"))},
          {"name":"Channel","pass":m.get("channel_id")==self.CHANNEL_ID,"detail":str(m.get("channel_id"))},
          {"name":"Profile","pass":m.get("profile")==self.PROFILE_ID,"detail":str(m.get("profile"))},
        ]
        return {"pass":all(x["pass"] for x in checks),"checks":checks,"resource_class":"LIGHT"}
    def job_spec(self,job_name,context): return None
    def artifacts(self,stage,context): return []
    def retry_policy(self,stage,failure,context): return {"retryable":False,"resume_point":None,"cache_reuse":False,"max_safe_retries":0,"human_intervention":True}
    def invoke_action(self,action,context,body):
        raise RuntimeError(f"{self.CHANNEL_ID} capability adapter is integrated, but action '{action}' requires the channel media/reasoning smoke phase.")
'''

CHANNELS={
"en_story":{
 "class":"ENStoryReferenceAdapter","aid":"EN_STORY_REFERENCE_ADAPTER_v1_0","cid":"EN_STORY","profile":"EN_DRAMA_v1","name":"English Story Longform","rules":["STORY_LONGFORM_EDITING_CANONICAL_RULES_v1_0"],
 "caps":{"voice":{"provider":"KOKORO","mode":"TWO_VOICE","roles":{"female":"af_heart","male":"am_liam"},"timeline_authority":"ACTUAL_GENERATED_WAV"},"editing":{"mode":"DIALOGUE_STORY_BEAT","static_first":True,"speaker_focus":True,"motion_scope":"VISUAL_RUN"},"subtitles":{"mode":"EXTERNAL_SRT","timing_authority":"ACTUAL_NARRATION_WAV"},"publishing":{"package_required":True},"visual":{"mode":"STORY_STILLS","speaker_focus_supported":True}}
},
"en_bts":{
 "class":"ENBTSReferenceAdapter","aid":"EN_BTS_REFERENCE_ADAPTER_v1_0","cid":"EN_BTS","profile":"EN_TECH_v1","name":"Between the Steps","rules":["BTS_CANONICAL_VISUAL_TEMPLATE_v1_1"],
 "caps":{"voice":{"provider":"KOKORO","mode":"SINGLE_DEFAULT","default_voice":"af_heart","timeline_authority":"ACTUAL_GENERATED_WAV"},"editing":{"mode":"INFORMATION_FIRST","visual_runs":"STRUCTURED_SHORTER"},"subtitles":{"mode":"EXTERNAL_SRT","timing_authority":"ACTUAL_NARRATION_WAV"},"publishing":{"package_required":True,"front_end_gate":"REVENUE_FIRST"},"visual":{"canonical":"BTS_CANONICAL_VISUAL_TEMPLATE_v1_1","containerless_default":True,"arrows_default":False,"subtitle_safe_y":[820,1080]}}
},
"jp_bts":{
 "class":"JPBTSReferenceAdapter","aid":"JP_BTS_REFERENCE_ADAPTER_v1_0","cid":"JP_BTS","profile":"JP_TECH_v1","name":"Japanese Between the Steps","rules":["LONGFORM_FACTORY_JP_VOICE_CASTING_POLICY_v1_0"],
 "caps":{"voice":{"provider":"VOICEVOX","mode":"MULTI_VOICE","allowed_pairings":["male/female","male/male","female/female"],"style_resolution":"DYNAMIC_BY_SPEAKER_AND_STYLE_NAME","timeline_authority":"ACTUAL_GENERATED_WAV"},"editing":{"mode":"INFORMATION_FIRST","role_mapping":"DETERMINISTIC_WITHIN_EPISODE"},"subtitles":{"mode":"EXTERNAL_SRT","language":"ja","timing_authority":"ACTUAL_GENERATED_WAV"},"publishing":{"package_required":True},"visual":{"mode":"STRUCTURED_TECH","subtitle_safe_required":True}}
}
}

REG={
 "registry_version":"1.6","contract":"LONGFORM_FACTORY_ADAPTER_CONTRACT_v1_0",
 "adapters":{
  "JP_STORY_REFERENCE_ADAPTER_v1_0":{"adapter_id":"JP_STORY_REFERENCE_ADAPTER_v1_0","module":"adapters.channels.jp_story.reference_adapter","class":"JPStoryReferenceAdapter","channel_id":"JP_STORY","profile":"JP_STORY_v1","status":"LEGACY_PINNED","requires":{"manifest_schema":">=1.2,<2.0","profile":"JP_STORY_v1"}},
  "JP_STORY_REFERENCE_ADAPTER_v1_1":{"adapter_id":"JP_STORY_REFERENCE_ADAPTER_v1_1","module":"adapters.channels.jp_story.reference_adapter_v11","class":"JPStoryReferenceAdapter","channel_id":"JP_STORY","profile":"JP_STORY_v1","status":"LEGACY_PINNED","requires":{"manifest_schema":">=1.2,<2.0","profile":"JP_STORY_v1"}},
  "JP_STORY_REFERENCE_ADAPTER_v1_2":{"adapter_id":"JP_STORY_REFERENCE_ADAPTER_v1_2","module":"adapters.channels.jp_story.reference_adapter_v12","class":"JPStoryReferenceAdapter","channel_id":"JP_STORY","profile":"JP_STORY_v1","status":"LEGACY_PINNED","requires":{"core_contract":">=1.0,<2.0","manifest_schema":">=1.2,<2.0","profile":"JP_STORY_v1"}},
  "JP_STORY_LEGACY_MEDIA_ADAPTER_v1_0":{"adapter_id":"JP_STORY_LEGACY_MEDIA_ADAPTER_v1_0","module":"adapters.channels.jp_story.legacy_media_adapter","class":"JPStoryLegacyMediaAdapter","channel_id":"JP_STORY","profile":"JP_STORY_v1","status":"LEGACY_PINNED","requires":{"core_contract":">=1.0,<2.0","manifest_schema":">=1.0,<1.2","profile":"JP_STORY_v1"}},
  "JP_STORY_REFERENCE_ADAPTER_v1_3":{"adapter_id":"JP_STORY_REFERENCE_ADAPTER_v1_3","module":"adapters.channels.jp_story.reference_adapter_v13","class":"JPStoryReferenceAdapter","channel_id":"JP_STORY","profile":"JP_STORY_v1","status":"LEGACY_PINNED","requires":{"core_contract":">=1.0,<2.0","manifest_schema":">=1.2,<2.0","profile":"JP_STORY_v1"}},
  "JP_STORY_LEGACY_MEDIA_ADAPTER_v1_1":{"adapter_id":"JP_STORY_LEGACY_MEDIA_ADAPTER_v1_1","module":"adapters.channels.jp_story.legacy_media_adapter_v11","class":"JPStoryLegacyMediaAdapter","channel_id":"JP_STORY","profile":"JP_STORY_v1","status":"LEGACY_PINNED","requires":{"core_contract":">=1.0,<2.0","manifest_schema":">=1.0,<1.2","profile":"JP_STORY_v1"}},
  "JP_STORY_REFERENCE_ADAPTER_v1_4":{"adapter_id":"JP_STORY_REFERENCE_ADAPTER_v1_4","module":"adapters.channels.jp_story.reference_adapter_v14","class":"JPStoryReferenceAdapter","channel_id":"JP_STORY","profile":"JP_STORY_v1","status":"ACTIVE_REFERENCE","requires":{"core_contract":">=1.0,<2.0","manifest_schema":">=1.2,<2.0","profile":"JP_STORY_v1"}},
  "JP_STORY_LEGACY_MEDIA_ADAPTER_v1_2":{"adapter_id":"JP_STORY_LEGACY_MEDIA_ADAPTER_v1_2","module":"adapters.channels.jp_story.legacy_media_adapter_v12","class":"JPStoryLegacyMediaAdapter","channel_id":"JP_STORY","profile":"JP_STORY_v1","status":"LEGACY_RUNTIME_COMPAT","requires":{"core_contract":">=1.0,<2.0","manifest_schema":">=1.0,<1.2","profile":"JP_STORY_v1"}}
 },
 "channels":{"JP_STORY":{"default_adapter":"JP_STORY_REFERENCE_ADAPTER_v1_4","profile":"JP_STORY_v1","status":"ACTIVE_REFERENCE","legacy_default_adapter":"JP_STORY_LEGACY_MEDIA_ADAPTER_v1_2","integration_status":"ACTIVE_MEDIA_REFERENCE"}}
}
for mod,c in CHANNELS.items():
    REG["adapters"][c["aid"]]={"adapter_id":c["aid"],"module":f"adapters.channels.{mod}.reference_adapter_v10","class":c["class"],"channel_id":c["cid"],"profile":c["profile"],"status":"ACTIVE_CAPABILITY","requires":{"core_contract":">=1.0,<2.0","manifest_schema":">=1.2,<2.0","profile":c["profile"]}}
    REG["channels"][c["cid"]]={"default_adapter":c["aid"],"profile":c["profile"],"status":"ACTIVE_CAPABILITY","media_binding":"PENDING_MEDIA_SMOKE"}

QA='''from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json
from shared_core.adapter_runtime import AdapterManager, AdapterError

EXPECTED={"JP_STORY":("JP_STORY_v1","JP_STORY_REFERENCE_ADAPTER_v1_4"),"EN_STORY":("EN_DRAMA_v1","EN_STORY_REFERENCE_ADAPTER_v1_0"),"EN_BTS":("EN_TECH_v1","EN_BTS_REFERENCE_ADAPTER_v1_0"),"JP_BTS":("JP_TECH_v1","JP_BTS_REFERENCE_ADAPTER_v1_0")}
def _m(cid,p): return {"schema_version":"1.2","channel_id":cid,"profile":p,"episode_id":cid+"_EP999","authority":{},"lifecycle":{"current_stage":"DISCOVERY"}}
def run_cross_channel_qa(root:Path):
 a=AdapterManager(Path(root)); checks=[]; matrix={}
 def add(n,ok,d=""): checks.append({"name":n,"status":"PASS" if ok else "FAIL","detail":str(d)})
 reg=a.registry(); add("Registry version",reg.get("registry_version")=="1.6",reg.get("registry_version"))
 for cid,(p,aid) in EXPECTED.items():
  m=_m(cid,p)
  try:
   resolved=a.adapter_id_for_manifest(m); desc=a.describe(m); add(cid+" default dispatch",resolved==aid and desc.get("channel_id")==cid and desc.get("profile_id")==p,f"{resolved} · {desc.get('integration_status','ACTIVE_REFERENCE')}"); matrix[cid]=desc
  except Exception as e: add(cid+" default dispatch",False,e); continue
  bad=_m(cid,"WRONG_PROFILE_v0"); rejected=False
  try: a.adapter_id_for_manifest(bad)
  except AdapterError: rejected=True
  add(cid+" profile isolation",rejected,"wrong profile rejected" if rejected else "wrong profile accepted")
 bad=_m("EN_STORY","EN_DRAMA_v1"); bad["authority"]["channel_adapter"]="JP_BTS_REFERENCE_ADAPTER_v1_0"; rejected=False
 try: a.describe(bad)
 except AdapterError: rejected=True
 add("Pinned adapter/channel isolation",rejected,"cross-channel pin rejected" if rejected else "cross-channel pin accepted")
 jp=reg.get("channels",{}).get("JP_STORY",{}); add("JP legacy compatibility preserved",jp.get("legacy_default_adapter")=="JP_STORY_LEGACY_MEDIA_ADAPTER_v1_2",jp.get("legacy_default_adapter"))
 pending=[cid for cid in ("EN_STORY","EN_BTS","JP_BTS") if matrix.get(cid,{}).get("media_binding")!="PENDING_MEDIA_SMOKE"]; add("No false media-complete claims",not pending,"pending media smoke explicitly declared")
 out={"schema":"LONGFORM_FACTORY_CROSS_CHANNEL_QA_v1","created_at":datetime.now(timezone.utc).isoformat(),"state":"PASS" if all(x["status"]=="PASS" for x in checks) else "FAIL","checks":checks,"matrix":matrix,"next_media_smoke_order":["EN_STORY","EN_BTS","JP_BTS"]}
 p=Path(root)/"factory"/"state"/"cross_channel_qa.json"; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8"); return out
'''

PAGE='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Channel Integration</title><style>body{margin:0;background:#f5f6f8;color:#15171a;font:14px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.wrap{max-width:1050px;margin:auto;padding:28px}.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.spacer{flex:1}.card{background:#fff;border:1px solid #e1e5ea;border-radius:14px;padding:18px;margin:14px 0}.btn{border:1px solid #d1d5db;background:#fff;border-radius:8px;padding:9px 12px;cursor:pointer}.primary{background:#111827;color:white;border-color:#111827}.muted{color:#667085}.pass{color:#067647}.fail{color:#b42318}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:9px;border-top:1px solid #eee;vertical-align:top}</style></head><body><div class="wrap"><div class="row"><div><h1 style="margin:0">Cross-Channel Integration</h1><div class="muted">4 profiles · registry isolation · media smoke readiness</div></div><div class="spacer"></div><button class="btn" onclick="location.href='/'">Dashboard</button></div><div class="card"><div class="row"><b id="state">NOT RUN</b><div class="spacer"></div><button class="btn primary" onclick="runqa()">Run Cross-Channel QA</button></div><div id="checks" style="margin-top:12px"></div></div><div class="card"><b>Channel Matrix</b><div id="matrix" style="margin-top:12px"></div></div><div class="card"><b>Next gate</b><div class="muted" style="margin-top:8px">Representative media smoke: EN_STORY → EN_BTS → JP_BTS. Existing episodes remain pinned and are not migrated.</div></div></div><script>function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}async function g(u){let r=await fetch(u,{cache:'no-store'});let x=await r.json();if(!r.ok||x.ok===false)throw new Error(x.error||x.message||'request failed');return x}async function p(u,b){let r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});let x=await r.json();if(!r.ok||x.ok===false)throw new Error(x.error||x.message||'request failed');return x}function render(x){document.getElementById('state').className=x.state==='PASS'?'pass':'fail';document.getElementById('state').textContent=x.state||'UNKNOWN';document.getElementById('checks').innerHTML=(x.checks||[]).map(c=>`<div class="${c.status==='PASS'?'pass':'fail'}">${c.status==='PASS'?'✓':'✕'} <b>${esc(c.name)}</b> <span class="muted">${esc(c.detail||'')}</span></div>`).join('');let rows=Object.entries(x.matrix||{}).map(([cid,d])=>`<tr><td><b>${esc(cid)}</b></td><td>${esc(d.profile_id)}</td><td>${esc(d.adapter_id)}</td><td>${esc(d.capabilities?.voice?.provider)}</td><td>${esc(d.capabilities?.voice?.mode)}</td><td>${esc(d.media_binding||'ACTIVE')}</td></tr>`).join('');document.getElementById('matrix').innerHTML=`<table><tr><th>Channel</th><th>Profile</th><th>Adapter</th><th>Voice</th><th>Mode</th><th>Media</th></tr>${rows}</table>`}async function load(){try{render(await g('/api/channel-integration/status'))}catch(e){}}async function runqa(){try{render(await p('/api/channel-integration/run',{}))}catch(e){alert(e.message)}}load();</script></body></html>'''

PROFILE={"schema":"LONGFORM_FACTORY_CHANNEL_PROFILE_MATRIX_v1","version":"1.0","status":"FINAL_LOCK","principles":{"core_must_not_branch_on_channel_for_production_semantics":True,"actual_generated_audio_is_timeline_authority":True,"external_subtitles_default":True,"publishing_package_required":True,"existing_episode_auto_migration":False},"profiles":{"JP_STORY_v1":{"channel_id":"JP_STORY","story_mode":"NARRATION_DRIVEN","voice_provider":"VOICEVOX","voice_cardinality":"SINGLE","casting":"MALE_OR_FEMALE_BY_EPISODE","editing":"STATIC_FIRST_STORY_BEAT","media_status":"ACTIVE_REFERENCE"},"EN_DRAMA_v1":{"channel_id":"EN_STORY","story_mode":"DIALOGUE_DRIVEN","voice_provider":"KOKORO","voice_cardinality":"TWO","casting":"af_heart + am_liam current canonical pair","editing":"STATIC_FIRST_STORY_BEAT_WITH_SPEAKER_FOCUS","media_status":"PENDING_SMOKE"},"EN_TECH_v1":{"channel_id":"EN_BTS","story_mode":"INFORMATION_FIRST","voice_provider":"KOKORO","voice_cardinality":"SINGLE_DEFAULT","visual_canonical":"BTS_CANONICAL_VISUAL_TEMPLATE_v1_1","editing":"STRUCTURED_VISUAL_RUNS","media_status":"PENDING_SMOKE"},"JP_TECH_v1":{"channel_id":"JP_BTS","story_mode":"INFORMATION_FIRST","voice_provider":"VOICEVOX","voice_cardinality":"TWO_CAPABLE","casting_pairings":["male/female","male/male","female/female"],"editing":"STRUCTURED_VISUAL_RUNS","media_status":"PENDING_SMOKE"}}}

SPEC='''# Longform Factory Cross-Channel Integration Spec v1.0

**Status:** FINAL LOCK
**Authority ID:** `LONGFORM_FACTORY_CROSS_CHANNEL_INTEGRATION_SPEC_v1_0`

Before Core v1 COMPLETE, EN_STORY, EN_BTS, JP_STORY and JP_BTS must operate as isolated channel profiles over one shared Core.

Phase 1:
- All four channels resolve through AdapterManager.
- Channel/profile mismatches fail.
- Core reads declared capabilities instead of embedding channel-specific production semantics.
- Existing Episode manifests are never auto-migrated.
- JP_STORY remains active media reference.
- EN_STORY / EN_BTS / JP_BTS are ACTIVE_CAPABILITY until representative media smoke passes.

Phase 2 media smoke order:
1. EN_STORY — Kokoro two-voice + Speaker Focus + actual-WAV subtitle timing.
2. EN_BTS — Kokoro information-first + BTS visual canonical + actual-WAV subtitle timing.
3. JP_BTS — VOICEVOX multi-voice role mapping + allowed gender pairings + actual-WAV subtitle timing.

No adapter may claim media readiness before its smoke test passes.
'''

AUTH={"authority_pointer_version":"1.7","status":"ACTIVE_CANDIDATE","scope":"Longform Factory Shared Core","supersedes":"LONGFORM_FACTORY_ACTIVE_AUTHORITY_v1_6","active_defaults":{"adapter_registry":"LONGFORM_FACTORY_ADAPTER_REGISTRY_v1_6","channel_profile_matrix":"LONGFORM_FACTORY_CHANNEL_PROFILE_MATRIX_v1_0","cross_channel_integration":"LONGFORM_FACTORY_CROSS_CHANNEL_INTEGRATION_SPEC_v1_0"},"channels":{"JP_STORY":{"default_profile":"JP_STORY_v1","adapter":"JP_STORY_REFERENCE_ADAPTER_v1_4","integration":"ACTIVE_MEDIA_REFERENCE"},"EN_STORY":{"default_profile":"EN_DRAMA_v1","adapter":"EN_STORY_REFERENCE_ADAPTER_v1_0","integration":"ACTIVE_CAPABILITY","media":"PENDING_SMOKE"},"EN_BTS":{"default_profile":"EN_TECH_v1","adapter":"EN_BTS_REFERENCE_ADAPTER_v1_0","integration":"ACTIVE_CAPABILITY","media":"PENDING_SMOKE"},"JP_BTS":{"default_profile":"JP_TECH_v1","adapter":"JP_BTS_REFERENCE_ADAPTER_v1_0","integration":"ACTIVE_CAPABILITY","media":"PENDING_SMOKE"}},"application_policy":{"existing_episode_auto_migration":"DISABLED","next_gate":"REPRESENTATIVE_MEDIA_SMOKE_EN_STORY_THEN_EN_BTS_THEN_JP_BTS","core_completion_target":"Idea to Upload Ready across four isolated channel profiles"}}

with zipfile.ZipFile(PREV_PKG) as z:
    cc=z.read("payload/control_center_current.py").decode("utf-8")
cc=cc.replace("from narrator_ab_lab import NarratorABLab","from narrator_ab_lab import NarratorABLab\nfrom cross_channel_integration import run_cross_channel_qa")
cc=cc.replace('UPDATES=UpdateManager(ROOT,APP_PATH,"1.9.9")','UPDATES=UpdateManager(ROOT,APP_PATH,"1.10.0")')
cc=cc.replace('<div class="ver">v1.9.9</div>','<div class="ver">v1.10.0</div>')
cc=cc.replace("Control Center v1.9.9 listening","Control Center v1.10.0 listening")
cc=cc.replace('"factory_version":"1.9.9"','"factory_version":"1.10.0"')
cc=cc.replace('<button class="topbtn" onclick="location.href=\'/qa\'">QA Lab</button>','<button class="topbtn" onclick="location.href=\'/qa\'">QA Lab</button><button class="topbtn" onclick="location.href=\'/channel-integration\'">Channels</button>',1)
ga='        if u.path=="/qa":\n'
gi='        if u.path=="/channel-integration":\n            p=ROOT/"factory"/"channel_integration_page.html"; raw=p.read_bytes(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(raw); return\n        if u.path=="/api/channel-integration/status":\n            p=ROOT/"factory"/"state"/"cross_channel_qa.json"\n            if p.exists(): self.send_json(load_json(p,{})); return\n            self.send_json({"state":"NOT_RUN","checks":[],"matrix":{}}); return\n'
cc=cc.replace(ga,gi+ga,1)
pa='            if self.path=="/api/updates/upload":\n'
pi='            if self.path=="/api/channel-integration/run":\n                try: self.send_json(run_cross_channel_qa(ROOT)); return\n                except Exception as e: self.send_json({"ok":False,"error":str(e)},400); return\n'
cc=cc.replace(pa,pi+pa,1)

files=[]
def add(src,target,text,mode="0644"):
    p=w(src,text)
    files.append((src,target,p,mode))

add("payload/adapters/channels/base_capability_adapter.py","factory/adapters/channels/base_capability_adapter.py",BASE_ADAPTER)
for mod,c in CHANNELS.items():
    src=f'from adapters.channels.base_capability_adapter import DeclarativeCapabilityAdapter\n\nclass {c["class"]}(DeclarativeCapabilityAdapter):\n    ADAPTER_ID={c["aid"]!r}\n    CHANNEL_ID={c["cid"]!r}\n    PROFILE_ID={c["profile"]!r}\n    DISPLAY_NAME={c["name"]!r}\n    REQUIRED_RULES={c["rules"]!r}\n    CAPABILITIES={c["caps"]!r}\n'
    add(f"payload/adapters/channels/{mod}/reference_adapter_v10.py",f"factory/adapters/channels/{mod}/reference_adapter_v10.py",src)
add("payload/adapters/adapter_registry.json","factory/adapters/adapter_registry.json",json.dumps(REG,ensure_ascii=False,indent=2)+"\n")
add("payload/canonical/LONGFORM_FACTORY_ADAPTER_REGISTRY_v1_6.json","factory/canonical/LONGFORM_FACTORY_ADAPTER_REGISTRY_v1_6.json",json.dumps(REG,ensure_ascii=False,indent=2)+"\n")
add("payload/canonical/LONGFORM_FACTORY_CHANNEL_PROFILE_MATRIX_v1_0.json","factory/canonical/LONGFORM_FACTORY_CHANNEL_PROFILE_MATRIX_v1_0.json",json.dumps(PROFILE,ensure_ascii=False,indent=2)+"\n")
add("payload/canonical/LONGFORM_FACTORY_CROSS_CHANNEL_INTEGRATION_SPEC_v1_0.md","factory/canonical/LONGFORM_FACTORY_CROSS_CHANNEL_INTEGRATION_SPEC_v1_0.md",SPEC)
add("payload/canonical/LONGFORM_FACTORY_ACTIVE_AUTHORITY_v1_7.json","factory/canonical/LONGFORM_FACTORY_ACTIVE_AUTHORITY_v1_7.json",json.dumps(AUTH,ensure_ascii=False,indent=2)+"\n")
add("payload/cross_channel_integration.py","factory/cross_channel_integration.py",QA)
add("payload/channel_integration_page.html","factory/channel_integration_page.html",PAGE)
add("payload/control_center_current.py","factory/control_center_current.py",cc,"0755")

for _,_,p,_ in files:
    if p.suffix==".py": py_compile.compile(str(p),doraise=True)

manifest={"schema":"LONGFORM_FACTORY_UPDATE_PACKAGE_v1","package_id":"LONGFORM_FACTORY_CROSS_CHANNEL_FOUNDATION_1_10_0","version":VERSION,"from_versions":[PREV],"channel":"dev","title":"Cross-Channel Integration Foundation","summary":"Registers all four channel profiles/adapters with isolation QA; media smoke remains explicit for EN_STORY, EN_BTS and JP_BTS.","server_script":"factory/control_center_current.py","files":[{"source":s,"target":t,"sha256":sha(p),"mode":m} for s,t,p,m in files],"delete":[]}
w("update_manifest.json",json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
w("release_notes.md","# Longform Factory v1.10.0 — Cross-Channel Integration Foundation\n\nEN_STORY, EN_BTS and JP_BTS move from PENDING to ACTIVE_CAPABILITY. JP_STORY remains active media reference. Adds Dashboard → Channels QA. No existing Episode manifest is migrated.\n")
OUT.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
    z.write(TMP/"update_manifest.json","update_manifest.json")
    for s,_,p,_ in files: z.write(p,s)
    z.write(TMP/"release_notes.md","release_notes.md")

digest=sha(OUT)
feed=json.loads((ROOT/"feed.json").read_text(encoding="utf-8"))
feed["generated_at"]=datetime.now(timezone.utc).isoformat()
feed["channels"]["dev"]={"version":VERSION,"package_url":f"https://raw.githubusercontent.com/Kapka87/longform-factory-updates/main/packages/{PKG_NAME}","package_sha256":digest,"updater_api_min":"1.1","published_at":datetime.now(timezone.utc).isoformat(),"title":"Cross-Channel Integration Foundation","summary":"Registers all four channel profiles/adapters with isolation QA; representative media smoke is next."}
(ROOT/"feed.json").write_text(json.dumps(feed,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"version":VERSION,"package":str(OUT),"sha256":digest},indent=2))
