---
name: extract-behance-moodboard
description: Extract and download full-resolution image modules from only the projects actually saved in a Behance moodboard. Use when a user provides a Behance moodboard URL or an open Chrome moodboard and asks to export, archive, scrape, or organize every saved project's images into project-named folders while excluding recommendations, covers, avatars, and related works.
---

# Extract Behance Moodboard

Extract a Behance moodboard through a manifest-first workflow. Treat the moodboard's saved-project grid as the only source of project scope, then download each project's body images at the highest available resolution.

## Required workflow

### 1. Inspect the moodboard in Chrome

- Use the `chrome:control-chrome` skill and read its complete instructions before browser work.
- Open or claim the exact moodboard URL supplied by the user.
- Identify the moodboard title, owner area, saved-project grid, and the boundary where the grid ends.
- Scope link extraction to the saved-project grid. Never query every `/gallery/` link across the whole document.
- Stop before `More Behance`, recommendations, similar work, author work, footer content, or infinite-scroll discovery sections.
- Deduplicate project cards by the numeric gallery ID while preserving moodboard order.

This boundary check is mandatory. A global selector can silently include dozens of recommendation cards.

### 2. Create the authoritative manifest

Write a UTF-8 JSON manifest before downloading anything:

```json
{
  "moodboard": "Board name",
  "moodboard_url": "https://www.behance.net/moodboard/123/example",
  "projects": [
    {
      "title": "Project name",
      "url": "https://www.behance.net/gallery/123456/Project-name"
    }
  ]
}
```

Use `image_urls` only for a project whose images must be recovered from the rendered Chrome page:

```json
{
  "title": "Special lazy-loaded project",
  "url": "https://www.behance.net/gallery/123456/Project-name",
  "image_urls": [
    "https://mir-s3-cdn-cf.behance.net/project_modules/1400_webp/example.png"
  ]
}
```

Before downloading, compare the manifest count with the visible saved-project grid. If the boundary or count is uncertain, pause and resolve it instead of guessing.

### 3. Download from the manifest

Run the bundled script with a Python runtime that has network access:

```powershell
python scripts/download_manifest.py --manifest <manifest.json> --output <output-folder> --workers 4
```

If `python` is unavailable, load the workspace dependencies and use the bundled Python executable.

The script:

- accepts either the object schema above or a legacy top-level project array;
- extracts only `mir-s3-cdn-cf.behance.net/project_modules/` assets;
- excludes `projects/404` covers, avatars, icons, recommendations, and author work;
- upgrades known renditions to `max_3840_webp`, then falls back to the discovered URL;
- numbers images in page order as `001`, `002`, and so on;
- preserves the actual response format: WebP, JPEG, PNG, or GIF;
- replaces Windows-invalid folder characters with readable full-width equivalents;
- uses retries, `.part` files, atomic rename, and existing-file skipping for safe resume;
- writes `_extract-summary.json` and returns a nonzero exit code when work remains.

Use `--probe-only --limit N` to test extraction without downloading images.

### 4. Recover special or newly published projects

If the script reports that a project has no body images:

1. Open that project in Chrome.
2. Trigger its lazy loading by scrolling through the project body when needed.
3. Inspect rendered `document.images` or the tab's `pageAssets` capability.
4. Keep only URLs containing `/project_modules/` from the project's main body.
5. Preserve DOM order and exclude recommendation covers.
6. Add the URLs to that manifest project's `image_urls` array.
7. Rerun the downloader; completed files will be skipped.

Do not infer missing URLs from filename patterns.

### 5. Validate the result

Require all of the following before reporting success:

- output project-folder count equals manifest project count;
- every project folder is nonempty;
- no folder exists for a project absent from the manifest;
- no `.part` files remain;
- `_extract-summary.json` reports no failed or partial projects;
- every downloaded image decodes successfully when Pillow is available.

Report the saved-project count, total image count, total size, validation result, and a clickable output-folder path.

## Safety and cleanup

- Work only with moodboards and projects the user can access through their normal Behance session and is permitted to save.
- Never bypass authentication, access controls, CAPTCHAs, paywalls, or geographic restrictions.
- Never inspect, copy, expose, or persist browser cookies, session tokens, passwords, or other credentials.
- Keep downloads local to the user-selected output folder. Do not upload, publish, or share extracted images unless the user separately requests that action and confirms they have the necessary rights.
- Never delete or alter folders outside the output root created for this extraction.
- If recommendations were accidentally downloaded, stop first, compute a dry-run removal list from the authoritative manifest, verify every resolved path remains inside the output root, and remove only the extra folders.
- Preserve unrelated user files and pre-existing work.
