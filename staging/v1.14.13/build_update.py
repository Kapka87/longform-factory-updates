from pathlib import Path
import runpy, subprocess, shutil
runpy.run_path("staging/v1.14.16/build_update.py", run_name="__main__")
shutil.copyfile("feed.v11416.json", "feed.v11413.json")
subprocess.run([
 "git","add",
 "packages/LONGFORM_FACTORY_UPDATER_CALLSITE_FIX_1_14_16.lfupdate.zip",
 "staging/v1.14.16/package_sha256.txt"
],check=True)
