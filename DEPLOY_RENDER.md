# Turnalyze - Render deployment notes

The app renders PDFs with **Playwright/Chromium** (DOCX -> PDF fallback and the
cover/AI-overview pages of every report). Everything else - upload, text
extraction, AI detection, database - is pure Python and works anywhere.

If Chromium cannot launch, the upload flow fails like this:

| File type | Failing stage | What the user sees |
| --- | --- | --- |
| DOCX / DOC | `convert_docx_to_pdf` (Playwright fallback) | redirect back to `/upload` (the flash message is not rendered by `templates/upload.html`) |
| PDF | `report_generator.create_report_pdf` | redirect to `/dashboard` via the 500 handler |

Both cases now log the **full traceback** plus the browser environment, so the
real Render error is visible in the Render logs.

---

## 1. Build command (Render Dashboard -> Settings -> Build & Deploy)

```bash
pip install --upgrade pip && pip install -r requirements.txt && python -m playwright install chromium
```

**No inline `PLAYWRIGHT_BROWSERS_PATH=` prefix needed.**  
`browser_runtime.py` detects Render native (`/opt/render/project` exists) and
forces `PLAYWRIGHT_BROWSERS_PATH=/opt/render/project/.cache/playwright` at
runtime, so build and runtime are guaranteed to use the same directory.

## 2. Start command (unchanged)

```bash
gunicorn --bind 0.0.0.0:$PORT --workers 1 --timeout 300 app:app
```

## 3. Environment variables

| Key | Value | Why |
| --- | --- | --- |
| `PLAYWRIGHT_BROWSERS_PATH` | `/opt/render/project/.cache/playwright` | Kept for documentation; `browser_runtime.py` forces this value on Render native if the env var is missing. |
| `PYTHON_VERSION` | `3.12.4` | Same as local. |
| `PYTHONUNBUFFERED` | `1` | Logs appear immediately. |
| `LOG_LEVEL` | `INFO` | `DEBUG` for even more detail. |
| `BROWSER_SELFTEST_ON_STARTUP` | `1` (default) | Logs a real Chromium launch result on every boot. Set to `0` to disable. |

### Never use these on Render

* `playwright install --with-deps` -> runs `su`/`sudo`, Render builds are
  unprivileged: `su: Authentication failure`.
* `apt-get install ...` in the build command -> same reason (no root).

Render native runtimes are **Debian 12 (bookworm)** and unprivileged; LibreOffice
therefore cannot be installed either, which is why the DOCX path relies on the
Playwright/Chromium fallback.

---

## 4. Verifying the deployment without shell access

```
GET https://<service>.onrender.com/health/browser?launch=1&deps=1
```

Returns, among others:

* `playwright_browsers_path` and `playwright_browsers_path_exists` — **must be the canonical path and `true`**
* `browsers_path_entries` (e.g. `chromium-1194`, `chromium_headless_shell-1194`)
* `chromium_browsers` - per browser: directory, executable, exists
* `chromium_executable` / `chromium_executable_exists`
* `chromium_headless_shell_executable` / `chromium_headless_shell_exists`
* `missing_shared_libraries` - the **exact** `.so` files Chromium cannot load
* `launch_test_ok` / `launch_test_message` - a real headless launch
* `playwright_install_deps_dry_run` - the apt packages Playwright asks for

> Playwright >= 1.49 ships two Chromium builds. `headless=True` (used by
> `pdf_converter.py` and `report_generator.py`) launches the **headless shell**
> by default, so `chromium_headless_shell_exists` must be `true` as well.
> `python -m playwright install chromium` installs both builds; `--only-shell`
> and `--no-shell` install only one of them - do not use those flags.

---

## 5. Upload pipeline log stages

Every upload logs these stages (`grep "Upload: stage="` in the Render logs):

```
stage=1_UPLOAD_RECEIVED
stage=2_FILE_SAVED
stage=3_BROWSER_ENVIRONMENT          (chromium path + missing libs)
stage=4_TEXT_EXTRACTION_START / _COMPLETE
stage=5_PDF_CONVERSION_START         (which converter will be tried)
stage=6_PLAYWRIGHT_LAUNCH_START      (pdf_converter / DOCX -> PDF)
stage=6_AI_DETECTION_START / _COMPLETE
stage=7_REPORT_GENERATION_START / _COMPLETE (FAILED + TRACEBACK)
stage=8_DB_REPORT_INSERT_START / _COMPLETE, 8_DB_REPORT_PATH_UPDATE
stage=9_REPORT_RENDERED
```

Failures additionally log `..._TRACEBACK` with the complete Python traceback and
`stage=BROWSER_ENVIRONMENT_AT_FAILURE`.

---

## 6. If `missing_shared_libraries` is not empty

The endpoint/logs name the exact libraries (for example `libnss3.so`,
`libatk-1.0.so.0`, `libgbm.so.1`). Because the native runtime has no root access,
you have two options:

1. **Docker runtime (recommended for this case).** Create a service from a
   Dockerfile based on `mcr.microsoft.com/playwright/python:v1.55.0-noble`, run
   `pip install -r requirements.txt`, copy the app and keep the *same* Gunicorn
   start command. The Playwright image ships every system library Chromium needs.
2. **Vendor the `.deb` libraries into the project.** Extract the missing
   packages into `./.pw-libs/root` (or `/opt/render/project/.cache/pw-libs/root`)
   during the build and set `LD_LIBRARY_PATH` to
   `.../.pw-libs/root/usr/lib/x86_64-linux-gnu`. `browser_runtime.py` already
   prepends those directories automatically, but it requires a writable apt
   mirror / `.deb` download during the build.

If `missing_shared_libraries` is empty and `launch_test_ok` is `true`, the
browser side is healthy and the failure is elsewhere in the pipeline; use the
stage logs above to pinpoint it.
