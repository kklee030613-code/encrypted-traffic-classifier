import argparse
import os
from pathlib import Path
import requests

ALLOWED_EXT = {".py", ".md", ".txt", ".csv", ".html", ".json"}
ALLOWED_NAMES = {".gitignore"}
EXCLUDE_DIRS = {".git", "__pycache__", ".venv", "models", "data/raw", "data/synthetic"}
EXCLUDE_FILES = {"set_env.ps1", "set_env.bat", "body.json", "models.json"}


def should_skip(rel_posix: str, path: Path) -> str | None:
    if path.name in EXCLUDE_FILES:
        return "excluded secret/temp file"
    for d in EXCLUDE_DIRS:
        if rel_posix == d or rel_posix.startswith(d + "/"):
            return f"excluded dir ({d})"
    if path.suffix.lower() not in ALLOWED_EXT and path.name not in ALLOWED_NAMES:
        return f"unsupported ext ({path.suffix or 'none'})"
    if path.stat().st_size == 0:
        return "empty file (0 bytes)"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace-id", default=None, help="기본 워크스페이스가 아닐 때만 URL의 workspace ID 입력")
    ap.add_argument("--dry-run", action="store_true", help="실제 업로드 없이 대상 목록만 확인")
    args = ap.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key and not args.dry_run:
        raise SystemExit("OPENROUTER_API_KEY 환경변수가 없습니다. '. .\\set_env.ps1' 먼저 실행하세요.")

    url = "https://openrouter.ai/api/v1/files"
    params = {"workspace_id": args.workspace_id} if args.workspace_id else {}
    headers = {"Authorization": f"Bearer {api_key}"}

    root = Path(".").resolve()
    ok = skip = fail = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        reason = should_skip(rel, path)
        if reason:
            print(f"[SKIP] {rel} ({reason})")
            skip += 1
            continue

        if args.dry_run:
            print(f"[PLAN] {rel} ({path.stat().st_size} bytes)")
            ok += 1
            continue

        with open(path, "rb") as f:
            resp = requests.post(
                url,
                params=params,
                headers=headers,
                files={"file": (rel, f)},
                timeout=60,
            )
        if resp.ok:
            fid = resp.json().get("id")
            print(f"[OK]   {rel} -> {fid}")
            ok += 1
        else:
            print(f"[FAIL] {rel} -> {resp.status_code} {resp.text[:150]}")
            fail += 1

    print(f"\n완료: 성공 {ok}개 / 건너뜀 {skip}개 / 실패 {fail}개")


if __name__ == "__main__":
    main()