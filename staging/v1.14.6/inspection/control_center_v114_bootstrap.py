#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import os, runpy, sys

ROOT=Path(os.environ.get("LONGFORM_FACTORY_ROOT",str(Path.home()/"Desktop"/"KohoroAudition"/"LongformFactory_v1_Production"))).expanduser().resolve()
qa_dir=ROOT/"factory"/"qa"
if str(qa_dir) not in sys.path:
    sys.path.insert(0,str(qa_dir))

src=ROOT/"factory"/"control_center_current.py"
text=src.read_text(encoding="utf-8")
if 'FACTORY_VERSION="1.13.0"' in text:
    text=text.replace('FACTORY_VERSION="1.13.0"','FACTORY_VERSION="1.14.5"',1)
elif 'FACTORY_VERSION="1.14.4"' not in text:
    raise RuntimeError("v1.14 bootstrap runtime-version anchor missing")

text=text.replace('if channel=="JP_STORY" and str(m.get("schema_version"))=="1.2":','if str(m.get("schema_version"))=="1.2":',1)

imp='from four_channel_production_integration import four_channel_production_status, run_four_channel_production_qa\n'
anchor='from cross_channel_media_smoke import media_smoke_status, run_media_smoke\n'
if imp.strip() not in text:
    if anchor not in text:
        raise RuntimeError("v1.14 bootstrap import anchor missing")
    text=text.replace(anchor,anchor+imp,1)

get_method='    def do_GET(self):\n'
get_route="""    def do_GET(self):
        if self.path.split("?",1)[0]=="/api/four-channel-production/status":
            self.send_json(four_channel_production_status(ROOT)); return
"""
if '/api/four-channel-production/status' not in text:
    if get_method not in text:
        raise RuntimeError("v1.14 do_GET anchor missing")
    text=text.replace(get_method,get_route,1)

post_method='    def do_POST(self):\n'
post_route="""    def do_POST(self):
        if self.path.split("?",1)[0]=="/api/four-channel-production/run":
            try:
                _body=self.read_body()
                self.send_json(run_four_channel_production_qa(ROOT),200); return
            except Exception as e:
                self.send_json({"ok":False,"error":"4-Channel Production QA failed: "+str(e)},400); return
"""
if '/api/four-channel-production/run' not in text:
    if post_method not in text:
        raise RuntimeError("v1.14 do_POST anchor missing")
    text=text.replace(post_method,post_route,1)

text=text.replace('<div class="ver">v1.13.0</div>','<div class="ver">v1.14.5</div>')
runtime=ROOT/"factory"/"state"/"control_center_v114_runtime.py"
runtime.parent.mkdir(parents=True,exist_ok=True)
runtime.write_text(text,encoding="utf-8")
runpy.run_path(str(runtime),run_name="__main__")
