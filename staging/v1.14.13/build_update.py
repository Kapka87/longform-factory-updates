from pathlib import Path
import runpy, subprocess, shutil
runpy.run_path("staging/v1.14.17/build_update.py", run_name="__main__")
shutil.copyfile("feed.v11417.json", "feed.v11413.json")
subprocess.run(["git","add","packages/LONGFORM_FACTORY_RUNTIME_AUTHORITY_RECOVERY_1_14_17.lfupdate.zip","staging/v1.14.17/package_sha256.txt"],check=True)
