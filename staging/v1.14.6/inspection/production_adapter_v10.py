from __future__ import annotations
from pathlib import Path
import json, urllib.request
from adapters.channels.production_adapter_common_v10 import ProductionLifecycleAdapter,_find_key,_write

class JPBTSProductionAdapter(ProductionLifecycleAdapter):
    ADAPTER_ID="JP_BTS_PRODUCTION_ADAPTER_v1_0"; CHANNEL_ID="JP_BTS"; PROFILE_ID="JP_TECH_v1"; DISPLAY_NAME="Japanese Between the Steps — Production"; ADAPTER_VERSION="1.0"; RUNNER_REL="factory/runners/jp_bts_production_media_v10.py"; SCRIPT_SCHEMA="JP_BTS_PRODUCTION_SCRIPT_v1"; MAPPING_SCHEMA="JP_BTS_VISUAL_MAPPING_v1"
    REQUIRED_RULES=["LONGFORM_FACTORY_JP_VOICE_CASTING_POLICY_v1_0"]
    CAPABILITIES={"reasoning":{"provider":"manual_handoff","provider_neutral":True,"revenue_first":True},"voice":{"provider":"VOICEVOX","mode":"MULTI_VOICE","style_resolution":"DYNAMIC_BY_SPEAKER_AND_STYLE_NAME","allowed_pairings":["male/female","male/male","female/female"],"timeline_authority":"ACTUAL_GENERATED_WAV","hardcoded_style_id":False},"editing":{"mode":"INFORMATION_FIRST","role_mapping":"DETERMINISTIC_WITHIN_EPISODE"},"subtitles":{"mode":"EXTERNAL_SRT","language":"ja","timing_authority":"ACTUAL_NARRATION_WAV"},"publishing":{"package_required":True,"front_end_gate":"REVENUE_FIRST"},"visual":{"mode":"STRUCTURED_TECH","subtitle_safe_required":True,"image_generation_binding":"PROVIDER_NEUTRAL"}}
    TASK_INSTRUCTIONS={
      "DISCOVERY":"Run revenue-first discovery for JP_BTS information-first longform. Return candidate_id, premise, market evidence, title/thumbnail hook, comparable evidence and channel fit in decisions[].",
      "RESEARCH":"Research the greenlit JP_BTS premise and separate verified facts, uncertainty, dates, numbers and source notes.","FACT_LOCK":"Create a JP_BTS Fact Lock using KEEP, DROP or NEED_REVIEW. Do not invent non-public system mechanics.",
      "SCRIPT":"Draft the complete Japanese information-first script. Return script_json in decisions[] with schema JP_BTS_PRODUCTION_SCRIPT_v1, casting roles using speaker_name + style_name + gender only (never style_id), and lines[{id,speaker,text,spoken_text,subtitle_text,pause_after}].",
      "SCRIPT_QC":"QC and correct the complete JP_BTS script. Return the full corrected script_json using JP_BTS_PRODUCTION_SCRIPT_v1. Preserve natural spoken Japanese and exact factual qualifiers.",
      "VISUAL_PLAN":"Plan structured information visuals. Return visual_mapping with schema JP_BTS_VISUAL_MAPPING_v1, visuals[{id,filename,role}], runs[{visual_id,line_start,line_end,motion:STATIC|SLOW_PUSH}]. Every line must be covered exactly once. Prefer simple spatial grouping and subtitle-safe layouts; no fragile connector geometry.",
      "VISUAL_QC":"QC JP_BTS final visual masters for factual scope, 1920x1080, hierarchy, subtitle safety and mapping completeness.","THUMBNAIL":"Define the final thumbnail for the completed JP_BTS video.","TITLE":"Create the final Japanese upload title.","DESCRIPTION":"Create the final Japanese description.","TAGS":"Create concise Japanese upload tags.","PUBLISHING_QC":"QC final video, thumbnail, title, description, tags and final upload SRT."
    }
    def _materialize_script(self,ep,m,result):
        data=_find_key(result,"script_json")
        if not isinstance(data,dict) or data.get("schema")!=self.SCRIPT_SCHEMA:raise RuntimeError("SCRIPT_QC result requires JP_BTS script_json")
        casting=data.get("casting") or {}; lines=data.get("lines") or []
        if not casting or not lines:raise RuntimeError("casting and lines required")
        for role,cfg in casting.items():
            if "style_id" in cfg:raise RuntimeError("Hard-coded VOICEVOX style_id is forbidden")
            if not cfg.get("speaker_name") or not cfg.get("style_name"):raise RuntimeError("speaker_name/style_name required for "+role)
        for i,row in enumerate(lines,1):
            if row.get("speaker") not in casting:raise RuntimeError(f"Unknown speaker line {i}")
            row.setdefault("id",f"L{i:03d}"); row.setdefault("spoken_text",row.get("text")); row.setdefault("subtitle_text",row.get("text")); row.setdefault("pause_after",0.35)
        eid=m["episode_id"]; p=Path(ep)/"input/script"/f"{eid}_SCRIPT_FINAL.json"; _write(p,data); (Path(ep)/"input/script"/f"{eid}_SCRIPT_FINAL.txt").write_text("\n".join(str(x.get("text") or x.get("spoken_text") or "") for x in lines)+"\n",encoding="utf-8"); return p
    def _unit_count(self,ep,m):
        p=Path(ep)/"input/script"/f"{m['episode_id']}_SCRIPT_FINAL.json"; return len(json.loads(p.read_text(encoding="utf-8")).get("lines") or []) if p.exists() else None
    def _validate_mapping(self,mapping,unit_count=None):
        if not isinstance(mapping,dict) or mapping.get("schema")!=self.MAPPING_SCHEMA:raise ValueError("visual_mapping schema invalid")
        ids={str(v.get("id")) for v in (mapping.get("visuals") or []) if isinstance(v,dict) and v.get("id") and v.get("filename")}; cover=[]
        if not ids:raise ValueError("visuals required")
        for r in mapping.get("runs") or []:
            if str(r.get("visual_id")) not in ids:raise ValueError("unknown visual")
            a=int(r.get("line_start",0)); b=int(r.get("line_end",0));
            if a<1 or b<a:raise ValueError("invalid line range")
            cover.extend(range(a,b+1))
        if unit_count is not None and sorted(cover)!=list(range(1,unit_count+1)):raise ValueError("runs must cover every line exactly once")
        return True
    def _media_extra_checks(self,ep,m):
        ok=False; detail="unavailable"
        try:
            with urllib.request.urlopen("http://127.0.0.1:50021/version",timeout=1.5) as r: detail=r.read().decode("utf-8","replace"); ok=True
        except Exception as e: detail=str(e)
        return [{"name":"VOICEVOX","pass":ok,"detail":detail}]
