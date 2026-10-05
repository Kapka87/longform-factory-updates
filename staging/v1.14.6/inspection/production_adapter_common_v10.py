from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import importlib.util, json, shutil, sys
from adapters.channels.base_capability_adapter import DeclarativeCapabilityAdapter

STAGES=["DISCOVERY","GREENLIGHT","RESEARCH","FACT_LOCK","SCRIPT","SCRIPT_QC","VISUAL_PLAN","VISUAL_BUILD","VISUAL_QC","VOICE","TIMING","SUBTITLES","EDIT_PLAN","RENDER","AUTO_QC","PREVIEW_REVIEW","FINAL","THUMBNAIL","TITLE","DESCRIPTION","TAGS","PUBLISHING_QC","PUBLISHING_REVIEW","UPLOAD_READY"]
REASONING_STAGES={"DISCOVERY","RESEARCH","FACT_LOCK","SCRIPT","SCRIPT_QC","VISUAL_PLAN","VISUAL_QC","THUMBNAIL","TITLE","DESCRIPTION","TAGS","PUBLISHING_QC"}
MEDIA_STAGES={"VOICE","TIMING","SUBTITLES","EDIT_PLAN","RENDER","AUTO_QC","PREVIEW_REVIEW","FINAL"}

def _now(): return datetime.now(timezone.utc).isoformat()
def resolve_executable(name):
    import os
    found = shutil.which(name)
    if found:
        return found
    for candidate in (f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}", f"/opt/local/bin/{name}"):
        p = Path(candidate)
        if p.is_file() and os.access(str(p), os.X_OK):
            return str(p)
    return None

def _read(path,default=None):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return {} if default is None else default
def _write(path,obj):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name(path.name+".tmp"); tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); tmp.replace(path)
def _find_key(obj,key):
    if isinstance(obj,dict):
        if key in obj:return obj[key]
        for v in obj.values():
            x=_find_key(v,key)
            if x is not None:return x
    elif isinstance(obj,list):
        for v in obj:
            x=_find_key(v,key)
            if x is not None:return x
    return None
def _locked(v): return str(v or "").upper().replace(" ","_") in {"LOCK","FINAL_LOCK","FINAL"}

class ProductionLifecycleAdapter(DeclarativeCapabilityAdapter):
    ADAPTER_VERSION="1.0"
    PRODUCTION_STATUS="ACTIVE_PRODUCTION"
    TASK_INSTRUCTIONS={}
    RUNNER_REL=""
    SCRIPT_SCHEMA=""
    MAPPING_SCHEMA=""

    def describe(self,context):
        out=super().describe(context); out.update({"adapter_id":self.ADAPTER_ID,"adapter_version":self.ADAPTER_VERSION,"production_status":self.PRODUCTION_STATUS,"integration_status":"ACTIVE_PRODUCTION","required_rules":list(self.REQUIRED_RULES),"capabilities":self.CAPABILITIES}); return out
    def _context_manifest(self,context):
        m=(context or {}).get("manifest")
        if not isinstance(m,dict): raise ValueError("manifest missing from adapter context")
        return m
    def _context_ep(self,context):
        for k in ("episode_path","episode_dir","ep"):
            if (context or {}).get(k): return Path(context[k])
        m=self._context_manifest(context); return self.root/"projects"/self.CHANNEL_ID/"episodes"/m["episode_id"]
    def _stage(self,m): return m.get("lifecycle",{}).get("current_stage","DISCOVERY")
    def _stage_state(self,m,stage=None):
        stage=stage or self._stage(m); return m.get("lifecycle",{}).get("stages",{}).get(stage,{}).get("runtime_state","NOT_STARTED")
    def _set_stage(self,m,stage,state,current=False,decision=None):
        lc=m.setdefault("lifecycle",{}); it=lc.setdefault("stages",{}).setdefault(stage,{}); it["runtime_state"]=state; it["updated_at"]=_now()
        if decision is not None: it["review_decision"]=decision
        if current: lc["current_stage"]=stage
    def _save_manifest(self,ep,m): _write(Path(ep)/"episode_manifest.json",m)
    def _reason_dir(self,ep): return Path(ep)/"work"/"reasoning"
    def _task_copy(self,ep,stage): return self._reason_dir(ep)/f"{stage}_task.json"
    def _result_copy(self,ep,stage): return self._reason_dir(ep)/f"{stage}_result.json"
    def _load_task(self,ep,stage): return _read(self._task_copy(ep,stage),{})
    def _load_result(self,ep,stage): return _read(self._result_copy(ep,stage),{})
    def _task_context(self,ep,m,stage): return {"adapter_id":self.ADAPTER_ID,"episode_id":m.get("episode_id"),"channel_id":self.CHANNEL_ID,"profile":self.PROFILE_ID,"stage":stage,"required_rules":list(self.REQUIRED_RULES),"episode_path":str(Path(ep))}
    def _script_status(self,m): return m.get("script",{}).get("status") or m.get("workstreams",{}).get("script",{}).get("status") or ""
    def _visual_status(self,m): return m.get("visuals",{}).get("status") or m.get("workstreams",{}).get("visuals",{}).get("status") or ""
    def _mapping_path(self,ep,m):
        d=Path(ep)/"work"/"visual_mapping"; xs=sorted(d.glob(f"{m.get('episode_id')}_VISUAL_MAPPING_v*.json")) if d.exists() else []; return xs[-1] if xs else d/f"{m.get('episode_id')}_VISUAL_MAPPING_v01.json"
    def _visual_dir(self,ep): return Path(ep)/"input"/"visuals"
    def _latest(self,folder,pattern):
        xs=[p for p in Path(folder).glob(pattern) if p.is_file()] if Path(folder).exists() else []; return max(xs,key=lambda p:p.stat().st_mtime) if xs else None
    def _media_extra_checks(self,ep,m): return []
    def preflight(self,stage,context):
        base=super().preflight(stage,context); m=self._context_manifest(context); ep=self._context_ep(context); checks=list(base.get("checks",[])); aid=m.get("authority",{}).get("channel_adapter"); checks.append({"name":"Pinned adapter","pass":aid==self.ADAPTER_ID,"detail":str(aid)})
        if stage in MEDIA_STAGES:
            media=self._media_binding(); checks.append({"name":self.CHANNEL_ID+" representative media smoke","pass":media=="ACTIVE_MEDIA_SMOKE","detail":media}); ss=self._script_status(m); vs=self._visual_status(m); checks.append({"name":"Script FINAL LOCK","pass":_locked(ss),"detail":ss or "missing"}); checks.append({"name":"Visual FINAL LOCK","pass":_locked(vs),"detail":vs or "missing"}); mp=self._mapping_path(ep,m); checks.append({"name":"Visual Mapping","pass":mp.exists(),"detail":str(mp)}); checks.extend(self._media_extra_checks(ep,m)); checks.append({"name":"ffmpeg","pass":bool(resolve_executable("ffmpeg")),"detail":resolve_executable("ffmpeg") or "missing"}); checks.append({"name":"ffprobe","pass":bool(resolve_executable("ffprobe")),"detail":resolve_executable("ffprobe") or "missing"})
        return {"pass":all(bool(x.get("pass")) for x in checks),"checks":checks,"resource_class":"HEAVY_RENDER" if stage in MEDIA_STAGES else self._resource_class(stage)}
    def _resource_class(self,stage):
        if stage in REASONING_STAGES:return "REASONING"
        if stage=="VOICE":return "TTS_SERVICE"
        if stage=="VISUAL_BUILD":return "IMAGE_GENERATION"
        if stage in {"RENDER","FINAL"}:return "HEAVY_RENDER"
        if stage=="AUTO_QC":return "QC"
        if stage in {"PUBLISHING_REVIEW","UPLOAD_READY"}:return "PUBLISHING"
        return "LIGHT"
    def _create_task(self,ep,m):
        stage=self._stage(m)
        if stage not in REASONING_STAGES: raise RuntimeError(stage+" is not a reasoning stage")
        old=self._load_task(ep,stage)
        if old and old.get("status")=="AWAITING_MANUAL_RESULT":return {"ok":True,"message":"Existing task reused","task_id":old.get("task_id")}
        import reasoning_provider_bridge as reasoning
        packet=reasoning.execute_task(self.root,task={"task_type":f"{self.CHANNEL_ID}_{stage}","channel_id":self.CHANNEL_ID,"episode_id":m.get("episode_id"),"instruction":self.TASK_INSTRUCTIONS.get(stage,f"Complete {self.CHANNEL_ID} {stage}."),"context":self._task_context(ep,m,stage)})
        _write(self._task_copy(ep,stage),packet); self._set_stage(m,stage,"BLOCKED",current=True); self._save_manifest(ep,m); return {"ok":True,"message":"Reasoning task prepared","task_id":packet.get("task_id")}
    def _get_prompt(self,ep,m):
        task=self._load_task(ep,self._stage(m))
        if not task: raise RuntimeError("Prepare the task first")
        return {"ok":True,"message":"Prompt ready","prompt_text":task.get("manual_prompt","")}
    def _materialize_script(self,ep,m,result): raise NotImplementedError
    def _validate_mapping(self,mapping,unit_count=None): raise NotImplementedError
    def _unit_count(self,ep,m): raise NotImplementedError
    def _advance_after_import(self,ep,m,stage,packet):
        result=packet.get("result",{})
        if result.get("status")=="FAIL": self._set_stage(m,stage,"FAILED",current=True); return
        if stage=="DISCOVERY": self._set_stage(m,"DISCOVERY","COMPLETE"); self._set_stage(m,"GREENLIGHT","NEEDS_REVIEW",current=True)
        elif stage=="RESEARCH": self._set_stage(m,"RESEARCH","COMPLETE"); self._set_stage(m,"FACT_LOCK","READY",current=True)
        elif stage=="FACT_LOCK":
            blocking=any(isinstance(x,dict) and str(x.get("decision","")).upper()=="NEED_REVIEW" for x in (result.get("decisions") or []))
            if blocking:self._set_stage(m,"FACT_LOCK","BLOCKED",current=True)
            else:self._set_stage(m,"FACT_LOCK","COMPLETE"); self._set_stage(m,"SCRIPT","READY",current=True)
        elif stage=="SCRIPT": self._set_stage(m,"SCRIPT","COMPLETE"); self._set_stage(m,"SCRIPT_QC","READY",current=True)
        elif stage=="SCRIPT_QC": self._set_stage(m,"SCRIPT_QC","NEEDS_REVIEW",current=True)
        elif stage=="VISUAL_PLAN":
            mapping=_find_key(result,"visual_mapping"); self._validate_mapping(mapping,self._unit_count(ep,m)); _write(self._mapping_path(ep,m),mapping); self._set_stage(m,"VISUAL_PLAN","COMPLETE"); self._set_stage(m,"VISUAL_BUILD","READY",current=True)
        elif stage=="VISUAL_QC": self._set_stage(m,"VISUAL_QC","NEEDS_REVIEW",current=True)
        elif stage=="THUMBNAIL": self._set_stage(m,"THUMBNAIL","COMPLETE"); self._set_stage(m,"TITLE","READY",current=True)
        elif stage=="TITLE": self._set_stage(m,"TITLE","COMPLETE"); self._set_stage(m,"DESCRIPTION","READY",current=True)
        elif stage=="DESCRIPTION": self._set_stage(m,"DESCRIPTION","COMPLETE"); self._set_stage(m,"TAGS","READY",current=True)
        elif stage=="TAGS": self._set_stage(m,"TAGS","COMPLETE"); self._set_stage(m,"PUBLISHING_QC","READY",current=True)
        elif stage=="PUBLISHING_QC": self._set_stage(m,"PUBLISHING_QC","NEEDS_REVIEW",current=True)
    def _import_result(self,ep,m,body):
        stage=self._stage(m); task=self._load_task(ep,stage)
        if not task: raise RuntimeError("No task prepared for current stage")
        raw=body.get("result"); result=json.loads(raw) if isinstance(raw,str) else raw
        if not isinstance(result,dict): raise ValueError("result JSON required")
        import reasoning_provider_bridge as reasoning
        packet=reasoning.execute_task(self.root,result=result,task_id=task.get("task_id")); _write(self._result_copy(ep,stage),packet); self._advance_after_import(ep,m,stage,packet); self._save_manifest(ep,m); return {"ok":True,"message":stage+" result imported"}
    def _greenlight(self,ep,m,body):
        if self._stage(m)!="GREENLIGHT":raise RuntimeError("Not at GREENLIGHT")
        d=str(body.get("decision","")).upper()
        if d not in {"GREENLIGHT","REWORK","DROP"}:raise ValueError("invalid decision")
        if d=="GREENLIGHT":self._set_stage(m,"GREENLIGHT","COMPLETE",decision=d); self._set_stage(m,"RESEARCH","READY",current=True)
        elif d=="REWORK":self._set_stage(m,"GREENLIGHT","COMPLETE",decision=d); self._set_stage(m,"DISCOVERY","READY",current=True)
        else:self._set_stage(m,"GREENLIGHT","DROPPED",decision=d); m.setdefault("lifecycle",{})["state"]="DROPPED"
        self._save_manifest(ep,m); return {"ok":True,"message":"Greenlight decision: "+d}
    def _approve_script(self,ep,m):
        if self._stage(m)!="SCRIPT_QC" or self._stage_state(m)!="NEEDS_REVIEW":raise RuntimeError("Script is not awaiting review")
        packet=self._load_result(ep,"SCRIPT_QC"); result=packet.get("result",packet); out=self._materialize_script(ep,m,result); m.setdefault("script",{})["status"]="FINAL_LOCK"; m.setdefault("workstreams",{}).setdefault("script",{})["status"]="FINAL_LOCK"; self._set_stage(m,"SCRIPT_QC","COMPLETE",decision="APPROVE"); self._set_stage(m,"VISUAL_PLAN","READY",current=True); self._save_manifest(ep,m); return {"ok":True,"message":"Script FINAL LOCK created","path":str(out)}
    def _rework_script(self,ep,m): self._set_stage(m,"SCRIPT_QC","COMPLETE",decision="REWORK"); self._set_stage(m,"SCRIPT","READY",current=True); self._save_manifest(ep,m); return {"ok":True,"message":"Script returned to rework"}
    def _validate_visual_files(self,ep,m):
        from PIL import Image
        mapping=_read(self._mapping_path(ep,m),{}); self._validate_mapping(mapping,self._unit_count(ep,m)); rows=[]
        for v in mapping.get("visuals",[]):
            if isinstance(v,dict) and v.get("filename"): rows.append((str(v.get("id") or ""),str(v["filename"])))
        if not rows:raise RuntimeError("No expected visuals")
        bad=[]
        for vid,fn in rows:
            p=self._visual_dir(ep)/fn
            if not p.exists():bad.append(vid+": missing "+fn);continue
            with Image.open(p) as im:
                if tuple(im.size)!=(1920,1080):bad.append(f"{vid}: {im.size}")
        if bad:raise RuntimeError("Visual validation failed: "+"; ".join(bad))
        self._set_stage(m,"VISUAL_BUILD","COMPLETE"); self._set_stage(m,"VISUAL_QC","READY",current=True); self._save_manifest(ep,m); return {"ok":True,"message":f"Visual import validated · {len(rows)} masters"}
    def _approve_visuals(self,ep,m):
        if self._stage(m)!="VISUAL_QC" or self._stage_state(m)!="NEEDS_REVIEW":raise RuntimeError("Visuals are not awaiting review")
        m.setdefault("visuals",{})["status"]="FINAL_LOCK"; m.setdefault("workstreams",{}).setdefault("visuals",{})["status"]="FINAL_LOCK"; self._set_stage(m,"VISUAL_QC","COMPLETE",decision="APPROVE"); self._set_stage(m,"VOICE","READY",current=True); self._save_manifest(ep,m); return {"ok":True,"message":"Visuals FINAL LOCK · media build ready"}
    def _approve_preview(self,ep,m):
        import hashlib
        if self._stage(m)!="PREVIEW_REVIEW" or self._stage_state(m)!="NEEDS_REVIEW":raise RuntimeError("Preview is not awaiting review")
        eid=m["episode_id"]; preview=self._latest(Path(ep)/"output/preview",f"{eid}_PREVIEW_v*.mp4"); srt=self._latest(Path(ep)/"work/srt",f"{eid}_UPLOAD_v*.srt"); qc=self._latest(Path(ep)/"output/preview",f"{eid}_QC_v*.json")
        if not preview or not srt or not qc or _read(qc,{}).get("status")!="PASS":raise RuntimeError("Preview/SRT/PASS QC artifact missing")
        outv=Path(ep)/"output/final"/f"{eid}_FINAL.mp4"; outs=Path(ep)/"output/publishing"/f"{eid}_UPLOAD_FINAL.srt"; outv.parent.mkdir(parents=True,exist_ok=True); outs.parent.mkdir(parents=True,exist_ok=True)
        if outv.exists() or outs.exists():raise RuntimeError("FINAL output already exists; silent overwrite blocked")
        shutil.copy2(preview,outv); shutil.copy2(srt,outs)
        def sh(p): h=hashlib.sha256(); h.update(Path(p).read_bytes()); return h.hexdigest()
        if sh(preview)!=sh(outv):raise RuntimeError("Final video promotion hash mismatch")
        m.setdefault("video",{})["status"]="FINAL_LOCK"; self._set_stage(m,"PREVIEW_REVIEW","COMPLETE",decision="APPROVE"); self._set_stage(m,"FINAL","COMPLETE"); self._set_stage(m,"THUMBNAIL","READY",current=True); self._save_manifest(ep,m); return {"ok":True,"message":"Preview promoted to FINAL · publishing front end ready","final":str(outv),"srt":str(outs)}
    def _publishing_files(self,ep,m):
        eid=m["episode_id"]; pub=Path(ep)/"output/publishing"
        return {"final":Path(ep)/"output/final"/f"{eid}_FINAL.mp4","srt":pub/f"{eid}_UPLOAD_FINAL.srt","thumbnail":pub/f"{eid}_THUMBNAIL_FINAL.png","title":pub/f"{eid}_TITLE.txt","description":pub/f"{eid}_DESCRIPTION.txt","tags":pub/f"{eid}_TAGS.txt"}
    def _approve_publishing(self,ep,m):
        from PIL import Image
        files=self._publishing_files(ep,m); missing=[k for k,p in files.items() if not p.exists()]
        if missing:raise RuntimeError("Publishing artifacts missing: "+", ".join(missing))
        with Image.open(files["thumbnail"]) as im:
            if tuple(im.size)!=(1280,720):raise RuntimeError("Thumbnail must be 1280x720")
        if not files["title"].read_text(encoding="utf-8").strip():raise RuntimeError("Title empty")
        self._set_stage(m,"PUBLISHING_QC","COMPLETE",decision="APPROVE"); self._set_stage(m,"PUBLISHING_REVIEW","COMPLETE",decision="APPROVE"); self._set_stage(m,"UPLOAD_READY","COMPLETE",current=True); m.setdefault("lifecycle",{})["state"]="COMPLETE"; m.setdefault("publishing",{})["status"]="FINAL_LOCK"; self._save_manifest(ep,m); return {"ok":True,"message":"Publishing Package FINAL LOCK · UPLOAD_READY"}
    def inspect(self,ep,m):
        stage=self._stage(m); state=self._stage_state(m,stage); task=self._load_task(ep,stage); result=self._load_result(ep,stage); buttons=[]; imp=False; candidates=[]; review=None; message="Production adapter active."
        if stage in REASONING_STAGES:
            if not task:buttons=[{"action":"create_task","label":"Prepare Task","primary":True}]
            elif task.get("status")=="AWAITING_MANUAL_RESULT" and not result:buttons=[{"action":"copy_prompt","label":"Copy Task Prompt","primary":True}]; imp=True
            elif stage=="SCRIPT_QC" and state=="NEEDS_REVIEW":buttons=[{"action":"approve_script","label":"Approve Script","primary":True},{"action":"rework_script","label":"Rework Script","primary":False}]
            elif stage=="VISUAL_QC" and state=="NEEDS_REVIEW":buttons=[{"action":"approve_visuals","label":"Approve Visuals","primary":True},{"action":"rework_visuals","label":"Rework Visuals","primary":False}]
            elif stage=="PUBLISHING_QC" and state=="NEEDS_REVIEW":buttons=[{"action":"approve_publishing","label":"Approve Publishing","primary":True},{"action":"open_publishing_folder","label":"Open Publishing Folder","primary":False}]
        if stage=="GREENLIGHT":
            r=self._load_result(ep,"DISCOVERY").get("result",{}); candidates=[x for x in (r.get("decisions") or []) if isinstance(x,dict) and x.get("candidate_id")]
        if stage=="VISUAL_BUILD":buttons=[{"action":"open_visual_folder","label":"Open Visual Folder","primary":True},{"action":"validate_visuals","label":"Validate Imported Visuals","primary":False}]; message="Import mapped 1920x1080 masters, then validate."
        if stage=="PREVIEW_REVIEW" and state=="NEEDS_REVIEW":buttons=[{"action":"approve_preview","label":"Approve Preview","primary":True},{"action":"rework_preview","label":"Rework Preview","primary":False}]; q=self._latest(Path(ep)/"output/preview",f"{m.get('episode_id')}_QC_v*.json"); review={"type":"PREVIEW","qc":_read(q,{}) if q else {}}
        return {"active":True,"adapter_id":self.ADAPTER_ID,"production_status":self.PRODUCTION_STATUS,"stage":stage,"state":state,"buttons":buttons,"task_exists":bool(task),"import_result":imp,"candidates":candidates,"review":review,"message":message}
    def next_action(self,context):
        m=self._context_manifest(context); ui=self.inspect(self._context_ep(context),m); b=(ui.get("buttons") or []); p=next((x for x in b if x.get("primary")),b[0] if b else None); return {"action":p.get("action") if p else "INSPECT","label":p.get("label") if p else "Inspect","stage":ui.get("stage"),"reason":ui.get("message")}
    def execute(self,stage,context,reporter=None): return {"stage":stage,"state":"BLOCKED","artifacts":[],"metrics":{},"warnings":["Use registered action/job path."],"next_recommended_action":"INSPECT"}
    def validate(self,stage,result,context):
        ok=isinstance(result,dict) and result.get("state") in {"COMPLETE","NEEDS_REVIEW","BLOCKED","FAILED"}; return {"pass":ok,"checks":[{"name":"Result envelope","pass":ok,"detail":stage}]}
    def artifacts(self,stage,context):return []
    def retry_policy(self,stage,failure,context):
        if stage in MEDIA_STAGES:return {"retryable":True,"resume_point":"VOICE","cache_reuse":True,"max_safe_retries":2,"human_intervention":False}
        return {"retryable":stage in REASONING_STAGES,"resume_point":stage if stage in REASONING_STAGES else None,"cache_reuse":stage in REASONING_STAGES,"max_safe_retries":2 if stage in REASONING_STAGES else 0,"human_intervention":True}
    def job_spec(self,job_name,context):
        if job_name not in {"BUILD_PREVIEW","BUILD_VOICE_ONLY"}:return None
        ep=self._context_ep(context); m=self._context_manifest(context); runner=self.root/self.RUNNER_REL; cmd=[sys.executable,str(runner),"--root",str(self.root),"--episode",str(ep)]
        if job_name=="BUILD_VOICE_ONLY":cmd.append("--voice-only")
        return {"job_name":job_name,"stage":"VOICE" if job_name=="BUILD_VOICE_ONLY" else "RENDER","resource_class":"TTS_SERVICE" if job_name=="BUILD_VOICE_ONLY" else "HEAVY_RENDER","runner":self.RUNNER_REL,"command":cmd,"cwd":str(self.root),"progress_path":str(Path(ep)/"work/job_status.json"),"retry_policy":self.retry_policy("VOICE" if job_name=="BUILD_VOICE_ONLY" else "RENDER",None,context),"episode_id":m.get("episode_id")}
    def invoke_action(self,action,context,body):
        m=self._context_manifest(context); ep=self._context_ep(context); action=str(action or "")
        if action=="create_task":return self._create_task(ep,m)
        if action=="get_prompt":return self._get_prompt(ep,m)
        if action=="import_result":return self._import_result(ep,m,body or {})
        if action=="greenlight":return self._greenlight(ep,m,body or {})
        if action=="approve_script":return self._approve_script(ep,m)
        if action=="rework_script":return self._rework_script(ep,m)
        if action=="open_visual_folder":d=self._visual_dir(ep); d.mkdir(parents=True,exist_ok=True); return {"ok":True,"message":"OPEN_TASK_PATH","path":str(d)}
        if action=="validate_visuals":return self._validate_visual_files(ep,m)
        if action=="approve_visuals":return self._approve_visuals(ep,m)
        if action=="rework_visuals":self._set_stage(m,"VISUAL_QC","COMPLETE",decision="REWORK"); self._set_stage(m,"VISUAL_PLAN","READY",current=True); self._save_manifest(ep,m); return {"ok":True,"message":"Visuals returned to Visual Plan"}
        if action=="approve_preview":return self._approve_preview(ep,m)
        if action=="rework_preview":self._set_stage(m,"PREVIEW_REVIEW","COMPLETE",decision="REWORK"); self._set_stage(m,"VOICE","READY",current=True); self._save_manifest(ep,m); return {"ok":True,"message":"Preview returned to media build"}
        if action=="open_publishing_folder":d=Path(ep)/"output/publishing"; d.mkdir(parents=True,exist_ok=True); return {"ok":True,"message":"OPEN_TASK_PATH","path":str(d)}
        if action=="approve_publishing":return self._approve_publishing(ep,m)
        raise RuntimeError("Unknown production action: "+action)
