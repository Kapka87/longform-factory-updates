from pathlib import Path
import runpy, subprocess, shutil

# Compatibility trigger: the existing trusted v1.14.13 publish workflow watches this path.
# Build the new v1.14.14 delta without overwriting the v1.14.13 package.
runpy.run_path("staging/v1.14.14/build_update.py", run_name="__main__")

# Existing workflow copies this compatibility feed name to feed.json.
shutil.copyfile("feed.v11414.json", "feed.v11413.json")

# Preserve staged additions when the existing workflow runs its own git add.
subprocess.run([
    "git","add",
    "packages/LONGFORM_FACTORY_GREENLIGHT_EPISODE_TARGET_FIX_1_14_14.lfupdate.zip",
    "staging/v1.14.14/package_sha256.txt"
], check=True)
