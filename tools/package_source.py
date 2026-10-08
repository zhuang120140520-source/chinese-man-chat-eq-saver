"""Create a reviewable source archive using Git's ignored-file boundary."""
import subprocess
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
paths = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                       cwd=root, check=True, stdout=subprocess.PIPE).stdout.decode("utf-8").split("\0")
out = root.parent / "partner-chat-source-0.6.1.zip"
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
    for relative in paths:
        if not relative:
            continue
        path = (root / relative).resolve()
        if not path.is_file():  # tracked upstream README was moved locally
            continue
        path.relative_to(root)
        if path.name == "config.json" or path.suffix in (".dpapi", ".env"):
            raise RuntimeError("Private file encountered; refusing to package")
        archive.write(path, "partner-chat-source/" + relative)
print("Source archive created; private config, encrypted profiles and QA images excluded.")
