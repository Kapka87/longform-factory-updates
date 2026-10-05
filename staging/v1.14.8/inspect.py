from pathlib import Path
import zipfile,re
p=Path("packages/LONGFORM_FACTORY_JP_BTS_DISCOVERY_UI_FIX_1_14_7.lfupdate.zip")
with zipfile.ZipFile(p) as z:
 s=z.read("payload/control_center_v114_bootstrap.py").decode()
print("BOOTSTRAP\n",s)
