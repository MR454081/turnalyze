"""Playwright / Chromium runtime configuration and diagnostics for Turnalyze.

WHY THIS MODULE EXISTS
----------------------
Turnalyze renders PDFs with Playwright/Chromium:

  * ``pdf_converter.convert_docx_to_pdf``  (DOCX -> PDF fallback path)
  * ``report_generator.create_report_pdf`` (cover page + AI overview page)

That works on a developer machine because the browser binaries were
downloaded once into the user cache.  A fresh deployment (Render) only
works when all three of the following are true:

  1. ``python -m playwright install chromium`` ran during the **build**,
  2. the **runtime** resolves the *same* browser directory the build wrote
     to (that is what ``PLAYWRIGHT_BROWSERS_PATH`` controls), and
  3. the shared libraries Chromium needs are present on the host.

This module keeps the build-time and the run-time browser directory in
sync and reports - in the application logs - exactly which of the three
conditions is not satisfied.

Nothing in this module raises: diagnostics must never take the app down.
"""

import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import threading
import time

logger = logging.getLogger(__name__)

BROWSERS_PATH_ENV = "PLAYWRIGHT_BROWSERS_PATH"
LIBRARY_PATH_ENV = "LD_LIBRARY_PATH"

# Render boots native services from /opt/render/project.  The build command
# in render.yaml installs Chromium into this directory so that the runtime -
# which is served from the same filesystem - finds it again.
RENDER_PROJECT_ROOT = "/opt/render/project"
RENDER_BROWSERS_PATH = os.path.join(RENDER_PROJECT_ROOT, ".cache", "playwright")
RENDER_SHARED_LIB_PATH = os.path.join(RENDER_PROJECT_ROOT, ".cache", "pw-libs")

# Optional project-local locations (see DEPLOY_RENDER.md).
LOCAL_BROWSERS_DIRNAME = ".playwright-browsers"
LOCAL_LIBS_DIRNAME = ".pw-libs"

# Playwright >= 1.49 installs two Chromium builds: the full browser and the
# headless shell.  Headless launches use the shell when it is available.
CHROMIUM_DIR_PREFIXES = ("chromium", "chromium_headless_shell")

_REPORT_CACHE = None


def project_dir():
    """Absolute path of the directory that contains this file."""
    return os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- browsers


def candidate_browsers_paths():
    """Every location where Playwright browsers may live, best guess first."""
    candidates = []
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(os.path.join(local_app_data, "ms-playwright"))
    else:
        candidates.append(RENDER_BROWSERS_PATH)
        xdg_cache = os.environ.get("XDG_CACHE_HOME")
        if xdg_cache:
            candidates.append(os.path.join(xdg_cache, "ms-playwright"))
        home = os.path.expanduser("~")
        if home and home != "~":
            candidates.append(os.path.join(home, ".cache", "ms-playwright"))
    candidates.append(os.path.join(project_dir(), LOCAL_BROWSERS_DIRNAME))

    unique = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


def _has_browser_binaries(path):
    """True when *path* contains a Playwright Chromium installation."""
    if not path or not os.path.isdir(path):
        return False
    try:
        entries = os.listdir(path)
    except OSError:
        return False
    for entry in entries:
        if entry.startswith(CHROMIUM_DIR_PREFIXES):
            if os.path.isdir(os.path.join(path, entry)):
                return True
    return False


def browsers_path_entries(path):
    """Directory names inside the resolved browsers path (for diagnostics)."""
    if not path or not os.path.isdir(path):
        return []
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def configure_browsers_path():
    """Point Playwright at the directory the build installed Chromium into.

    The environment variable is only set when the operator has not set it
    already, so an explicit Render environment variable always wins.

    On Render native, we *force* the path to /opt/render/project/.cache/playwright
    so build and runtime are guaranteed to agree, even if the env var was not
    propagated to the Gunicorn process.
    """
    existing = (os.environ.get(BROWSERS_PATH_ENV) or "").strip()
    if existing:
        logger.info(
            "Browser runtime: %s is set explicitly to %s (exists=%s).",
            BROWSERS_PATH_ENV, existing, os.path.isdir(existing),
        )
        return existing

    # Render native: force the canonical path so build+runtime match.
    if os.path.isdir(RENDER_PROJECT_ROOT):
        canonical = RENDER_BROWSERS_PATH
        os.environ[BROWSERS_PATH_ENV] = canonical
        logger.info(
            "Browser runtime: on Render, pinning %s to canonical path %s "
            "(exists=%s).",
            BROWSERS_PATH_ENV, canonical, os.path.isdir(canonical),
        )
        return canonical

    for candidate in candidate_browsers_paths():
        if _has_browser_binaries(candidate):
            os.environ[BROWSERS_PATH_ENV] = candidate
            logger.info(
                "Browser runtime: found Playwright Chromium in %s and pinned "
                "%s to it.", candidate, BROWSERS_PATH_ENV,
            )
            return candidate

    logger.warning(
        "Browser runtime: no Playwright Chromium installation found. "
        "Probed: %s. Chromium cannot launch until the build command runs "
        "'python -m playwright install chromium' with the same %s value that "
        "the runtime uses.",
        candidate_browsers_paths(), BROWSERS_PATH_ENV,
    )
    return (os.environ.get(BROWSERS_PATH_ENV) or "").strip()


# ------------------------------------------------------- system libraries


def candidate_shared_library_dirs():
    """Directories that may hold Chromium libraries extracted without root."""
    subdir_names = (
        "usr/lib/x86_64-linux-gnu",
        "usr/lib/aarch64-linux-gnu",
        "usr/lib64",
        "usr/lib",
        "lib/x86_64-linux-gnu",
        "lib",
    )
    roots = [
        os.path.join(RENDER_SHARED_LIB_PATH, "root"),
        os.path.join(project_dir(), LOCAL_LIBS_DIRNAME, "root"),
        RENDER_SHARED_LIB_PATH,
        os.path.join(project_dir(), LOCAL_LIBS_DIRNAME),
    ]
    directories = []
    for root in roots:
        directories.append(root)
        for subdir in subdir_names:
            directories.append(os.path.join(root, subdir))
    return directories


def configure_shared_library_path():
    """Prepend locally extracted Chromium libraries to ``LD_LIBRARY_PATH``.

    Inert unless a deployment step extracted the missing Debian packages into
    one of ``candidate_shared_library_dirs`` (see DEPLOY_RENDER.md).
    """
    if os.name != "posix":
        return os.environ.get(LIBRARY_PATH_ENV, "")

    found = [d for d in candidate_shared_library_dirs() if os.path.isdir(d)]
    if not found:
        return os.environ.get(LIBRARY_PATH_ENV, "")

    current = [p for p in (os.environ.get(LIBRARY_PATH_ENV) or "").split(":") if p]
    for directory in reversed(found):
        if directory not in current:
            current.insert(0, directory)
    os.environ[LIBRARY_PATH_ENV] = ":".join(current)
    logger.info(
        "Browser runtime: prepended local Chromium library directories to %s: %s",
        LIBRARY_PATH_ENV, found,
    )
    return os.environ[LIBRARY_PATH_ENV]


def missing_shared_libraries(executable):
    """Exact shared libraries Chromium is missing on this host.

    Uses ``ldd`` and returns entries reported as "not found" (for example
    ``libnss3.so``).  This is the authoritative answer to "which system
    libraries are missing" - it does not guess package names.
    """
    if os.name != "posix" or not executable or not os.path.isfile(executable):
        return []

    ldd = shutil.which("ldd") or "/usr/bin/ldd"
    if not os.path.isfile(ldd):
        logger.warning(
            "Browser runtime: 'ldd' is unavailable; cannot list missing "
            "shared libraries for %s.", executable,
        )
        return []

    try:
        result = subprocess.run(
            [ldd, executable],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception as exc:
        logger.warning(
            "Browser runtime: 'ldd %s' failed (%s: %s).",
            executable, type(exc).__name__, exc,
        )
        return []

    missing = []
    for line in ((result.stdout or "") + (result.stderr or "")).splitlines():
        stripped = line.strip()
        if "=> not found" in stripped:
            missing.append(stripped.split("=>")[0].strip())
        elif stripped.endswith("not found"):
            missing.append(stripped.split(":")[0].strip())
    return sorted({name for name in missing if name})


def required_system_packages():
    """Ask Playwright which apt packages Chromium needs (no root needed).

    ``install-deps --dry-run`` only *prints* the command it would run.  It is
    used by the ``/health/browser?deps=1`` diagnostic endpoint so the exact
    package list can be read straight from the Render logs.
    """
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "playwright",
                "install-deps", "--dry-run", "chromium",
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except Exception as exc:
        return "unavailable (%s: %s)" % (type(exc).__name__, exc)
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if not output:
        return "no output (exit code %s)" % result.returncode
    return output


# ------------------------------------------------------------ diagnostics


def _registry_revisions():
    """``{browser_name: revision}`` from playwright's browsers.json (if any)."""
    try:
        import playwright
    except Exception:
        return {}
    base = os.path.dirname(os.path.abspath(playwright.__file__))
    registry = os.path.join(base, "driver", "package", "browsers.json")
    if not os.path.isfile(registry):
        return {}
    try:
        with open(registry, "r", encoding="utf-8") as registry_file:
            data = json.load(registry_file)
    except Exception as exc:
        logger.warning(
            "Browser runtime: could not read %s (%s: %s).",
            registry, type(exc).__name__, exc,
        )
        return {}
    revisions = {}
    for entry in data.get("browsers") or []:
        name = entry.get("name")
        revision = entry.get("revision")
        if name and revision:
            revisions[name] = str(revision)
    return revisions


def _browser_directories(browsers_path):
    """``{browser_name: directory}`` for the Chromium builds on disk."""
    directories = {}
    if not browsers_path or not os.path.isdir(browsers_path):
        return directories
    try:
        entries = os.listdir(browsers_path)
    except OSError:
        return directories

    revisions = _registry_revisions()
    for prefix, name in (
        ("chromium_headless_shell-", "chromium-headless-shell"),
        ("chromium-", "chromium"),
    ):
        candidates = []
        revision = revisions.get(name)
        if revision:
            candidates.append("%s%s" % (prefix, revision))
        for entry in entries:
            if entry.startswith(prefix) and entry not in candidates:
                candidates.append(entry)
        for folder in candidates:
            directory = os.path.join(browsers_path, folder)
            if os.path.isdir(directory):
                directories[name] = directory
                break
    return directories


def _executable_names(browser_name):
    """Possible file names of the browser binary, per platform.

    Playwright's binaries are named differently per platform and version:
      * full Chromium   : ``chrome`` / ``chrome.exe`` / ``Chromium`` (macOS)
      * headless shell  : ``headless_shell`` (Linux) or
                          ``chrome-headless-shell.exe`` (Windows)
    """
    if os.name == "nt":
        if browser_name == "chromium":
            return ("chrome.exe",)
        return ("chrome-headless-shell.exe", "headless_shell.exe")
    if browser_name == "chromium":
        return ("chrome", "Chromium")
    return ("headless_shell", "chrome-headless-shell")


def _find_browser_binary(browser_dir, names):
    """Locate the browser binary inside *browser_dir* (layout agnostic)."""
    if not browser_dir or not os.path.isdir(browser_dir):
        return ""
    for root, _dirs, files in os.walk(browser_dir):
        for name in names:
            if name in files:
                return os.path.join(root, name)
    return ""


def chromium_browser_info():
    """Chromium + headless-shell directories/binaries, without any subprocess."""
    browsers_path = (os.environ.get(BROWSERS_PATH_ENV) or "").strip()
    info = {}
    for name, directory in _browser_directories(browsers_path).items():
        binary = _find_browser_binary(directory, _executable_names(name))
        info[name] = {
            "directory": directory,
            "executable": binary,
            "exists": bool(binary) and os.path.isfile(binary),
        }
    return info


def _driver_chromium_path(timeout=20):
    """Ask the Playwright driver for the path (slow: spawns the Node driver)."""
    box = {"path": "", "error": None}

    def _resolve():
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                box["path"] = str(playwright.chromium.executable_path or "")
        except Exception as exc:
            box["error"] = exc

    thread = threading.Thread(target=_resolve, name="chromium-path", daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        logger.warning(
            "Browser runtime: the Playwright driver did not answer within %ss "
            "while resolving the Chromium path.", timeout,
        )
        return ""
    if box["error"] is not None:
        logger.warning(
            "Browser runtime: the Playwright driver could not resolve the "
            "Chromium path (%s: %s).", type(box["error"]).__name__, box["error"],
        )
        return ""
    return box["path"]


def chromium_executable_path(timeout=20):
    """Path of the Chromium binary, or an empty string when unavailable.

    Resolution is filesystem based (fast, no subprocess) so application
    startup can never be blocked by the Playwright driver.  The driver is only
    consulted when browser directories exist but no binary was found inside
    them (a partial/corrupt installation).
    """
    browsers_path = (os.environ.get(BROWSERS_PATH_ENV) or "").strip()
    browsers = chromium_browser_info()

    for name in ("chromium", "chromium-headless-shell"):
        entry = browsers.get(name)
        if entry and entry["exists"]:
            return entry["executable"]

    if not browsers_path or not os.path.isdir(browsers_path):
        logger.warning(
            "Browser runtime: no Playwright browsers installed at %s yet. "
            "The build command must run 'python -m playwright install "
            "chromium' with the same %s value used at runtime.",
            browsers_path or "<unset>", BROWSERS_PATH_ENV,
        )
        return ""

    if browsers:
        return _driver_chromium_path(timeout=timeout)

    logger.warning(
        "Browser runtime: %s exists but contains no chromium directory "
        "(entries=%s).",
        browsers_path, browsers_path_entries(browsers_path),
    )
    return ""


def soffice_path():
    """LibreOffice path if installed (DOC/DOCX primary converter)."""
    try:
        from pdf_converter import _find_soffice
    except Exception as exc:
        return "unavailable (%s: %s)" % (type(exc).__name__, exc)
    try:
        return _find_soffice() or ""
    except Exception as exc:
        return "unavailable (%s: %s)" % (type(exc).__name__, exc)


def _docx2pdf_available():
    """True when the Windows/Word docx2pdf converter could be used."""
    try:
        import pdf_converter
    except Exception:
        return False
    return bool(
        pdf_converter.pythoncom is not None
        and pdf_converter.convert is not None
    )


def browser_environment_report(refresh=False):
    """Dictionary describing everything PDF generation depends on."""
    global _REPORT_CACHE
    if _REPORT_CACHE is not None and not refresh:
        return dict(_REPORT_CACHE)

    browsers_path = (os.environ.get(BROWSERS_PATH_ENV) or "").strip()
    browsers = chromium_browser_info()
    executable = chromium_executable_path()
    headless_shell = (browsers.get("chromium-headless-shell") or {}).get(
        "executable", "",
    )

    report = {
        "platform": "%s %s (%s)" % (
            platform.system(), platform.release(), platform.machine(),
        ),
        "python_version": platform.python_version(),
        "is_render": os.path.isdir(RENDER_PROJECT_ROOT),
        "playwright_browsers_path": browsers_path,
        "playwright_browsers_path_exists": (
            os.path.isdir(browsers_path) if browsers_path else False
        ),
        "browsers_path_entries": browsers_path_entries(browsers_path),
        "chromium_browsers": browsers,
        "chromium_executable": executable,
        "chromium_executable_exists": (
            bool(executable) and os.path.isfile(executable)
        ),
        "chromium_headless_shell_executable": headless_shell,
        "chromium_headless_shell_exists": (
            bool(headless_shell) and os.path.isfile(headless_shell)
        ),
        "missing_shared_libraries": missing_shared_libraries(executable),
        "ld_library_path": os.environ.get(LIBRARY_PATH_ENV, ""),
        "soffice": soffice_path(),
        "docx2pdf_available": _docx2pdf_available(),
    }
    _REPORT_CACHE = dict(report)
    return report


def browser_summary():
    """Compact one-line summary, safe to embed in log records."""
    report = browser_environment_report()
    missing = report.get("missing_shared_libraries") or []
    return (
        "playwright_browsers_path=%s browsers_path_exists=%s "
        "chromium_executable=%s chromium_exists=%s headless_shell_exists=%s "
        "missing_shared_libraries=%s ld_library_path=%s"
        % (
            report["playwright_browsers_path"] or "<unset>",
            report["playwright_browsers_path_exists"],
            report["chromium_executable"] or "<unknown>",
            report["chromium_executable_exists"],
            report["chromium_headless_shell_exists"],
            ",".join(missing) or "none",
            report["ld_library_path"] or "<empty>",
        )
    )


def runtime_diagnostics_text(refresh=False):
    """Multi-line diagnostics block for startup logging / endpoints."""
    report = browser_environment_report(refresh=refresh)
    lines = ["browser runtime diagnostics:"]
    for key in sorted(report):
        lines.append("  %s=%s" % (key, report[key]))
    return "\n".join(lines)


# ------------------------------------------------------------- self tests


def launch_self_test(timeout=60):
    """Really launch Chromium headless.  Returns ``(ok, message)``."""
    box = {"ok": False, "message": "not started"}
    started = time.time()

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return False, "playwright import failed: %s: %s" % (type(exc).__name__, exc)

    def _run():
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-gpu",
                        "--disable-dev-shm-usage",
                    ],
                )
                try:
                    page = browser.new_page()
                    page.set_content(
                        "<html><body>turnalyze self-test</body></html>"
                    )
                finally:
                    try:
                        browser.close()
                    except Exception:
                        pass
            box["ok"] = True
            box["message"] = "chromium launched and closed in %.1fs" % (
                time.time() - started
            )
        except Exception as exc:
            box["ok"] = False
            box["message"] = "%s: %s" % (type(exc).__name__, exc)

    thread = threading.Thread(target=_run, name="browser-selftest-run", daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        return False, "chromium launch self-test timed out after %ss" % timeout
    return bool(box["ok"]), str(box["message"])


def start_background_launch_self_test():
    """Log a real Chromium launch result shortly after boot (non-blocking).

    Enabled by default so the Render logs always show whether Chromium can
    actually launch in the deployed runtime.  Set
    ``BROWSER_SELFTEST_ON_STARTUP=0`` to switch it off.
    """
    if (os.environ.get("BROWSER_SELFTEST_ON_STARTUP") or "1").strip().lower() in (
        "0", "false", "no", "off",
    ):
        logger.info(
            "Browser runtime: startup Chromium self-test disabled by environment."
        )
        return None

    def _worker():
        ok, message = launch_self_test(timeout=90)
        if ok:
            logger.info(
                "Browser runtime: startup Chromium launch self-test PASSED (%s). %s",
                message, browser_summary(),
            )
        else:
            logger.error(
                "Browser runtime: startup Chromium launch self-test FAILED. "
                "reason=%s. %s", message, browser_summary(),
            )

    thread = threading.Thread(target=_worker, name="browser-selftest", daemon=True)
    thread.start()
    return thread


def configure_browser_runtime():
    """Configure browser path + library path before Chromium is used."""
    configure_shared_library_path()
    return configure_browsers_path()
