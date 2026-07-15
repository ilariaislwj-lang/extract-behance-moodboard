from __future__ import annotations

import argparse
import concurrent.futures
import html
import json
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/136 Safari/537.36"
)
IMAGE_URL_RE = re.compile(
    r"https://mir-s3-cdn-cf\.behance\.net/project_modules/[^\s\)\]\}\>\"']+",
    re.IGNORECASE,
)
GALLERY_ID_RE = re.compile(r"/gallery/(\d+)(?:/|$)")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
CONTENT_EXTENSIONS = {
    "image/webp": ".webp",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
}
INVALID_TRANSLATION = str.maketrans(
    {
        "<": "＜",
        ">": "＞",
        ":": "：",
        '"': "＂",
        "/": "／",
        "\\": "＼",
        "|": "｜",
        "?": "？",
        "*": "＊",
    }
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Behance project-module images from an authoritative moodboard manifest."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--probe-only",
        action="store_true",
        help="Discover image counts without downloading files.",
    )
    return parser.parse_args()


def open_url(url: str, timeout: int = 180):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
    )
    return urllib.request.urlopen(request, timeout=timeout)


def fetch_text(url: str) -> str:
    last_error: Exception | None = None
    for delay in (0, 2, 5, 10):
        if delay:
            time.sleep(delay)
        try:
            with open_url(url, timeout=120) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"failed to read project page: {last_error}")


def load_manifest(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        metadata: dict[str, Any] = {}
        raw_projects = data
    elif isinstance(data, dict) and isinstance(data.get("projects"), list):
        metadata = {key: value for key, value in data.items() if key != "projects"}
        raw_projects = data["projects"]
    else:
        raise ValueError("manifest must be a project array or an object with a projects array")

    projects: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_projects, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"project {index} is not an object")
        title = str(raw.get("title", "")).strip()
        url = str(raw.get("url", "")).strip()
        match = GALLERY_ID_RE.search(url)
        if not title or not match:
            raise ValueError(f"project {index} needs a title and a Behance gallery URL")
        project_id = match.group(1)
        if project_id in seen_ids:
            continue
        seen_ids.add(project_id)
        image_urls = raw.get("image_urls") or []
        if not isinstance(image_urls, list):
            raise ValueError(f"project {index} image_urls must be an array")
        projects.append(
            {
                "title": title,
                "url": url,
                "id": project_id,
                "image_urls": [str(item).strip() for item in image_urls if str(item).strip()],
            }
        )
    return metadata, projects


def safe_folder_name(title: str, project_id: str, used: set[str]) -> str:
    name = re.sub(r"\s+", " ", title).strip().translate(INVALID_TRANSLATION)
    name = name.rstrip(" .")[:90].rstrip(" .") or f"project_{project_id}"
    candidate = name
    if candidate.casefold() in used:
        candidate = f"{name}_{project_id}"
    used.add(candidate.casefold())
    return candidate


def normalize_image_urls(urls: list[str]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        url = html.unescape(raw).rstrip(".,;")
        parsed = urllib.parse.urlsplit(url)
        if parsed.netloc.lower() != "mir-s3-cdn-cf.behance.net":
            continue
        if not parsed.path.startswith("/project_modules/"):
            continue
        if Path(parsed.path).suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if url not in seen:
            seen.add(url)
            found.append(url)
    return found


def discover_images(project: dict[str, Any]) -> list[str]:
    if project["image_urls"]:
        return normalize_image_urls(project["image_urls"])
    source = project["url"].removeprefix("https://").removeprefix("http://")
    markdown = fetch_text("https://r.jina.ai/http://" + source)
    return normalize_image_urls(IMAGE_URL_RE.findall(markdown))


def highest_resolution(url: str) -> str:
    return re.sub(
        r"/project_modules/[^/]+/",
        "/project_modules/max_3840_webp/",
        url,
        count=1,
    )


def existing_image(folder: Path, index: int) -> Path | None:
    prefix = f"{index:03d}."
    for path in folder.iterdir():
        if (
            path.is_file()
            and path.name.startswith(prefix)
            and not path.name.endswith(".part")
            and path.stat().st_size > 0
        ):
            return path
    return None


def download_image(
    preferred_url: str, fallback_url: str, folder: Path, index: int
) -> tuple[str, Path]:
    current = existing_image(folder, index)
    if current is not None:
        return "skipped", current

    candidates = [preferred_url] if preferred_url == fallback_url else [preferred_url, fallback_url]
    last_error: Exception | None = None
    for candidate in candidates:
        for delay in (0, 2, 5):
            if delay:
                time.sleep(delay)
            temporary = folder / f"{index:03d}.part"
            try:
                with open_url(candidate) as response:
                    content_type = response.headers.get_content_type().lower()
                    if not content_type.startswith("image/"):
                        raise RuntimeError(f"response is not an image: {content_type}")
                    extension = CONTENT_EXTENSIONS.get(
                        content_type,
                        Path(urllib.parse.urlsplit(candidate).path).suffix.lower() or ".img",
                    )
                    final = folder / f"{index:03d}{extension}"
                    with temporary.open("wb") as output:
                        shutil.copyfileobj(response, output, length=1024 * 1024)
                if temporary.stat().st_size == 0:
                    raise RuntimeError("empty download")
                temporary.replace(final)
                return "downloaded", final
            except Exception as exc:
                last_error = exc
                temporary.unlink(missing_ok=True)
    raise RuntimeError(str(last_error))


def verify_image(path: Path) -> str | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as image:
            image.verify()
        return None
    except Exception as exc:
        return str(exc)


def process_project(
    project: dict[str, Any], output: Path, probe_only: bool
) -> dict[str, Any]:
    images = discover_images(project)
    if not images:
        raise RuntimeError("no project-module images found; recover URLs from rendered Chrome DOM")

    if probe_only:
        return {
            "title": project["title"],
            "url": project["url"],
            "image_count": len(images),
            "status": "probed",
        }

    folder = output / project["folder"]
    folder.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    skipped = 0
    failures: list[dict[str, Any]] = []
    verification_errors: list[dict[str, str]] = []

    for index, discovered_url in enumerate(images, start=1):
        try:
            status, path = download_image(
                highest_resolution(discovered_url), discovered_url, folder, index
            )
            downloaded += status == "downloaded"
            skipped += status == "skipped"
            verification_error = verify_image(path)
            if verification_error:
                verification_errors.append(
                    {"file": str(path), "error": verification_error}
                )
        except Exception as exc:
            failures.append(
                {"index": index, "url": discovered_url, "error": str(exc)}
            )

    status = "complete"
    if failures or verification_errors:
        status = "partial"
    return {
        "title": project["title"],
        "url": project["url"],
        "folder": str(folder),
        "image_count": len(images),
        "downloaded": downloaded,
        "skipped": skipped,
        "failed_images": failures,
        "verification_errors": verification_errors,
        "status": status,
    }


def main() -> int:
    args = parse_args()
    metadata, projects = load_manifest(args.manifest)
    if args.limit is not None:
        projects = projects[: max(args.limit, 0)]
    if not projects:
        raise SystemExit("manifest contains no projects")
    if args.workers < 1 or args.workers > 12:
        raise SystemExit("workers must be between 1 and 12")

    default_name = safe_folder_name(
        str(metadata.get("moodboard") or args.manifest.stem), "output", set()
    )
    output = (args.output or args.manifest.parent / f"{default_name}_behance_images").resolve()
    if not args.probe_only:
        output.mkdir(parents=True, exist_ok=True)

    used: set[str] = set()
    for project in projects:
        project["folder"] = safe_folder_name(project["title"], project["id"], used)

    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {
            executor.submit(process_project, project, output, args.probe_only): project
            for project in projects
        }
        completed = 0
        for future in concurrent.futures.as_completed(future_map):
            project = future_map[future]
            completed += 1
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "title": project["title"],
                    "url": project["url"],
                    "image_count": 0,
                    "downloaded": 0,
                    "skipped": 0,
                    "failed_images": [],
                    "verification_errors": [],
                    "status": "failed",
                    "error": str(exc),
                }
            results.append(result)
            print(
                f"[{completed}/{len(projects)}] {project['title']} | "
                f"images={result['image_count']} status={result['status']}",
                flush=True,
            )

    order = {project["url"]: index for index, project in enumerate(projects)}
    results.sort(key=lambda item: order[item["url"]])
    if args.probe_only:
        failed = sum(item["status"] == "failed" for item in results)
        print(
            json.dumps(
                {
                    "project_count": len(results),
                    "discovered_images": sum(item["image_count"] for item in results),
                    "failed_projects": failed,
                },
                ensure_ascii=False,
            )
        )
        return 1 if failed else 0

    summary = {
        **metadata,
        "manifest": str(args.manifest.resolve()),
        "output": str(output),
        "project_count": len(results),
        "complete_projects": sum(item["status"] == "complete" for item in results),
        "partial_projects": sum(item["status"] == "partial" for item in results),
        "failed_projects": sum(item["status"] == "failed" for item in results),
        "image_count": sum(item["image_count"] for item in results),
        "downloaded": sum(item.get("downloaded", 0) for item in results),
        "skipped": sum(item.get("skipped", 0) for item in results),
        "results": results,
    }
    (output / "_extract-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 1 if summary["partial_projects"] or summary["failed_projects"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
