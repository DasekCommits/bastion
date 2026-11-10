import hashlib
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "bastion"
WEB = ROOT / "web"
OUT = ROOT / "build" / "web"
TERMINAL_ONLY = {"__main__.py", "play.py", "look.py", "picker.py", "waf_cli.py", "waf.py", "tuning.py", "gamelog.py"}


def package(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(SOURCE.rglob("*")):
            if "__pycache__" in path.parts or path.is_dir():
                continue
            if path.suffix == ".py" and path.name in TERMINAL_ONLY:
                continue
            if path.suffix not in (".py", ".json"):
                continue
            archive.write(path, Path("bastion") / path.relative_to(SOURCE))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.iterdir():
        shutil.rmtree(old) if old.is_dir() else old.unlink()
    package(OUT / "bastion.zip")
    digest = hashlib.sha256()
    for path in [OUT / "bastion.zip", WEB / "app.js", WEB / "style.css", WEB / "index.html"]:
        digest.update(path.read_bytes())
    version = digest.hexdigest()[:10]
    (OUT / "app.js").write_text((WEB / "app.js").read_text(encoding="utf-8").replace("__VERSION__", version), encoding="utf-8")
    shutil.copy(WEB / "style.css", OUT / "style.css")
    shutil.copytree(WEB / "api", OUT / "api")
    html = (WEB / "index.html").read_text(encoding="utf-8")
    html = html.replace('href="style.css"', f'href="style.css?v={version}"').replace('src="app.js"', f'src="app.js?v={version}"')
    (OUT / "index.html").write_text(html, encoding="utf-8")
    print(f"Built {OUT} (version {version})")


if __name__ == "__main__":
    main()
