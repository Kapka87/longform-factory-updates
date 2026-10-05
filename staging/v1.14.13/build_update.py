from pathlib import Path
import runpy, subprocess, shutil

# Compatibility trigger for the existing trusted publisher.
runpy.run_path("staging/v1.14.15/build_update.py", run_name="__main__")
shutil.copyfile("feed.v11415.json", "feed.v11413.json")
subprocess.run([
    "git","add",
    "packages/LONGFORM_FACTORY_GREENLIGHT_PANEL_TARGET_FIX_1_14_15.lfupdate.zip",
    "staging/v1.14.15/package_sha256.txt"
], check=True)
