"""
CONTROLLED SAME-ENGINE COMPARISON
Tests A (browser-mode) vs Tests B (pdf-mode) using the EXACT SAME
Playwright Chromium instance, viewport, fonts, and image files.
The ONLY difference is: <body> vs <body class="pdf-mode">
"""
import os
import sys
import re
import json

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright
import numpy as np
from PIL import Image, ImageChops

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
CSS_PATH = os.path.join(STATIC_DIR, "css", "report.css")
COMPARE_DIR = os.path.join(BASE_DIR, "controlled_compare")
os.makedirs(COMPARE_DIR, exist_ok=True)

def fake_url_for(endpoint, **values):
    if endpoint == "static":
        filename = values.get("filename", "")
        abs_path = os.path.abspath(os.path.join(STATIC_DIR, filename))
        return "file:///" + abs_path.replace("\\", "/")
    if endpoint == "download_report":
        return f"/download/{values.get('report_id')}"
    if endpoint == "report_preview":
        return f"/report-preview/{values.get('report_id')}"
    return f"/{endpoint}"

env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html", "xml"]))
env.globals["url_for"] = fake_url_for

with open(CSS_PATH, "r", encoding="utf-8") as f:
    css_content = f.read()

# Shared test data
ctx = {
    "report_id": 999,
    "filename": "Analysis_report.pdf",
    "submission_date": "21 Aug 2026 12:00 PM",
    "upload_date": "21 Aug 2026 12:00 PM",
    "download_date": "21 Aug 2026 12:00 PM",
    "submission_id": "trn:oid:::1234:567890123",
    "pages": 20,
    "words": 1250,
    "characters": 7500,
    "file_size": "0.45 MB",
    "ai_score": 68,
    "human_score": 32,
    "status": "Completed",
    "html_content": "",
    "ai_only": 45,
    "ai_paraphrased": 23,
    "page_count": 22,
    "pdf_filename": "Analysis_report.pdf",
    "pdf_url": "/report-preview/999",
    "university": "Turnalyze University",
    "report_path": "",
}

# Generate HTML for both modes
ctx["for_pdf"] = False
html_browser = env.get_template("report.html").render(**ctx)

ctx["for_pdf"] = True
html_pdf = env.get_template("report.html").render(**ctx)

# Embed CSS (matching report_generator.py approach)
css_tag = '<style id="turnalyze-report-css">\n' + css_content + '\n</style>'
html_browser = re.sub(r'<link[^>]+report\.css[^>]*>', css_tag, html_browser, flags=re.IGNORECASE)
html_pdf = re.sub(r'<link[^>]+report\.css[^>]*>', css_tag, html_pdf, flags=re.IGNORECASE)

# Save temp HTML files
browser_html = os.path.join(BASE_DIR, "test_ctrl_browser.html")
pdf_html = os.path.join(BASE_DIR, "test_ctrl_pdf.html")
with open(browser_html, "w", encoding="utf-8") as f:
    f.write(html_browser)
with open(pdf_html, "w", encoding="utf-8") as f:
    f.write(html_pdf)

# Elements to inspect
PAGE1_ELEMENTS = [
    ".cover-page", ".cover-header", ".cover-content", ".cover-file-title",
    ".cover-meta", ".cover-details-wrapper", ".cover-details",
    ".cover-stats", ".cover-footer",
]
PAGE2_ELEMENTS = [
    ".overview-page", ".overview-page .header", ".summary", ".summary-left",
    ".notice-box", ".groups", ".disclaimer", ".faq",
    ".faq-left", ".faq-right", ".faq-image", ".footer",
]
ALL_ELEMENTS = PAGE1_ELEMENTS + PAGE2_ELEMENTS

COMPUTED_PROPS = [
    "display", "position", "width", "height", "margin", "padding", "gap",
    "fontFamily", "fontSize", "fontWeight", "lineHeight", "color",
    "backgroundColor", "border", "boxShadow",
    "flexDirection", "alignItems", "justifyContent",
]

def file_url(path):
    return "file:///" + os.path.abspath(path).replace("\\", "/")

RESULTS = {}

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=[
        "--allow-file-access-from-files",
        "--disable-web-security",
    ])

    viewport = {"width": 1280, "height": 4000}

    # === TEST A: Browser mode (for_pdf=False, no pdf-mode class) ===
    print("=" * 60)
    print("TEST A: BROWSER MODE (for_pdf=False, body has no class)")
    print("=" * 60)

    ctx_a = browser.new_context(viewport=viewport, device_scale_factor=1)
    page_a = ctx_a.new_page()
    page_a.emulate_media(media="screen")
    page_a.goto(file_url(browser_html), wait_until="networkidle")
    page_a.wait_for_timeout(1000)

    # Wait for images
    page_a.evaluate("() => Array.from(document.images).every(img => img.complete)")
    page_a.wait_for_timeout(500)

    body_class_a = page_a.evaluate("() => document.body.className")
    print(f"Body class: '{body_class_a}'")

    # Check download bar visibility
    dl_bar = page_a.evaluate("""
        () => {
            const el = document.querySelector('.report-download-bar');
            if (!el) return null;
            return { exists: true, display: getComputedStyle(el).display, visibility: getComputedStyle(el).visibility };
        }
    """)
    print(f"Download bar: {dl_bar}")

    # Screenshot Page 1
    cover_rect_a = page_a.evaluate("""
        () => {
            const r = document.querySelector('.cover-page').getBoundingClientRect();
            return {x: r.x, y: r.y, width: r.width, height: r.height};
        }
    """)
    print(f"Cover page rect: {cover_rect_a}")

    browser_p1_path = os.path.join(COMPARE_DIR, "browser_mode_page1.png")
    page_a.screenshot(path=browser_p1_path, clip=cover_rect_a, scale="css")
    print(f"Saved: {browser_p1_path}")

    # Screenshot Page 2
    overview_rect_a = page_a.evaluate("""
        () => {
            const r = document.querySelector('.overview-page').getBoundingClientRect();
            return {x: r.x, y: r.y, width: r.width, height: r.height};
        }
    """)
    print(f"Overview page rect: {overview_rect_a}")

    browser_p2_path = os.path.join(COMPARE_DIR, "browser_mode_page2.png")
    page_a.screenshot(path=browser_p2_path, clip=overview_rect_a, scale="css")
    print(f"Saved: {browser_p2_path}")

    # Collect element-level data
    browser_layout = page_a.evaluate(f"""
        () => {{
            const selectors = {ALL_ELEMENTS};
            const props = {COMPUTED_PROPS};
            const result = {{}};
            for (const sel of selectors) {{
                const el = document.querySelector(sel);
                if (!el) {{ result[sel] = {{exists: false}}; continue; }}
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                const rect = {{x: r.x, y: r.y, width: r.width, height: r.height, top: r.top, bottom: r.bottom, left: r.left, right: r.right}};
                const computed = {{}};
                for (const p of props) {{ computed[p] = s[p]; }}
                result[sel] = {{exists: true, rect: rect, computed: computed}};
            }}
            return result;
        }}
    """)

    # Logo investigation
    logo_info_a = page_a.evaluate("""
        () => {
            const logos = document.querySelectorAll('img');
            const results = [];
            for (const img of logos) {
                results.push({
                    src: img.src,
                    naturalWidth: img.naturalWidth,
                    naturalHeight: img.naturalHeight,
                    width: img.width,
                    height: img.height,
                    complete: img.complete,
                    boundingRect: img.getBoundingClientRect(),
                    selector: img.className || img.id,
                });
            }
            return results;
        }
    """)
    print(f"\nImages found: {len(logo_info_a)}")
    for img in logo_info_a:
        print(f"  src={img['src']}, natural={img['naturalWidth']}x{img['naturalHeight']}, rendered={img['width']}x{img['height']}, complete={img['complete']}")

    ctx_a.close()

    # === TEST B: PDF mode (for_pdf=True, body class="pdf-mode") ===
    print("\n" + "=" * 60)
    print("TEST B: PDF MODE (for_pdf=True, body class='pdf-mode')")
    print("=" * 60)

    ctx_b = browser.new_context(viewport=viewport, device_scale_factor=1)
    page_b = ctx_b.new_page()
    page_b.emulate_media(media="screen")
    page_b.goto(file_url(pdf_html), wait_until="networkidle")
    page_b.wait_for_timeout(1000)

    page_b.evaluate("() => Array.from(document.images).every(img => img.complete)")
    page_b.wait_for_timeout(500)

    # Remove download bar (matching report_generator.py JS)
    page_b.evaluate("""
        () => {
            const downloadBar = document.querySelector('.report-download-bar');
            if (downloadBar) downloadBar.remove();
            const container = document.getElementById('pdf-container');
            if (container) container.remove();
            document.querySelectorAll('.page-break').forEach(el => el.remove());
        }
    """)
    page_b.wait_for_timeout(300)

    body_class_b = page_b.evaluate("() => document.body.className")
    print(f"Body class: '{body_class_b}'")

    # Check pdf-mode body styles
    body_styles_b = page_b.evaluate("""
        () => {
            const s = getComputedStyle(document.body);
            return { margin: s.margin, padding: s.padding, background: s.backgroundColor };
        }
    """)
    print(f"Body styles: {body_styles_b}")

    # Screenshot Page 1
    cover_rect_b = page_b.evaluate("""
        () => {
            const r = document.querySelector('.cover-page').getBoundingClientRect();
            return {x: r.x, y: r.y, width: r.width, height: r.height};
        }
    """)
    print(f"Cover page rect: {cover_rect_b}")

    pdf_p1_path = os.path.join(COMPARE_DIR, "pdf_mode_page1.png")
    page_b.screenshot(path=pdf_p1_path, clip=cover_rect_b, scale="css")
    print(f"Saved: {pdf_p1_path}")

    # Screenshot Page 2
    overview_rect_b = page_b.evaluate("""
        () => {
            const r = document.querySelector('.overview-page').getBoundingClientRect();
            return {x: r.x, y: r.y, width: r.width, height: r.height};
        }
    """)
    print(f"Overview page rect: {overview_rect_b}")

    pdf_p2_path = os.path.join(COMPARE_DIR, "pdf_mode_page2.png")
    page_b.screenshot(path=pdf_p2_path, clip=overview_rect_b, scale="css")
    print(f"Saved: {pdf_p2_path}")

    # Collect element-level data
    pdf_layout = page_b.evaluate(f"""
        () => {{
            const selectors = {ALL_ELEMENTS};
            const props = {COMPUTED_PROPS};
            const result = {{}};
            for (const sel of selectors) {{
                const el = document.querySelector(sel);
                if (!el) {{ result[sel] = {{exists: false}}; continue; }}
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                const rect = {{x: r.x, y: r.y, width: r.width, height: r.height, top: r.top, bottom: r.bottom, left: r.left, right: r.right}};
                const computed = {{}};
                for (const p of props) {{ computed[p] = s[p]; }}
                result[sel] = {{exists: true, rect: rect, computed: computed}};
            }}
            return result;
        }}
    """)

    ctx_b.close()
    browser.close()

# === PIXEL-LEVEL COMPARISON ===
print("\n" + "=" * 60)
print("PIXEL-LEVEL COMPARISON")
print("=" * 60)

for page_num, (browser_path, pdf_path, label) in [
    (1, (browser_p1_path, pdf_p1_path, "PAGE 1 (Cover)")),
    (2, (browser_p2_path, pdf_p2_path, "PAGE 2 (Overview)"))
]:
    print(f"\n--- {label} ---")

    browser_img = Image.open(browser_path).convert("RGB")
    pdf_img = Image.open(pdf_path).convert("RGB")

    bw, bh = browser_img.size
    pw, ph = pdf_img.size
    print(f"Browser: {bw}x{bh}, PDF: {pw}x{ph}")

    # Resize to same dimensions
    w = min(bw, pw)
    h = min(bh, ph)
    browser_resized = browser_img.resize((w, h))
    pdf_resized = pdf_img.resize((w, h))

    arr_b = np.array(browser_resized, dtype=np.int16)
    arr_p = np.array(pdf_resized, dtype=np.int16)

    diff = np.abs(arr_b - arr_p)
    diff_mag = np.mean(diff, axis=2)
    diff_mask = diff_mag > 20

    total = w * h
    diff_count = np.sum(diff_mask)
    diff_pct = diff_count / total * 100

    print(f"Differing pixels (>20): {diff_count}/{total} ({diff_pct:.4f}%)")

    # Create diff image
    diff_viz = np.zeros((h, w, 3), dtype=np.uint8)
    diff_viz[diff_mask] = [255, 0, 0]
    diff_pil = Image.fromarray(diff_viz)
    diff_blended = Image.blend(browser_resized, diff_pil, alpha=0.4)
    diff_blended.save(os.path.join(COMPARE_DIR, f"page{page_num}_controlled_diff.png"))

    # Also save individual images
    browser_resized.save(os.path.join(COMPARE_DIR, f"browser_mode_page{page_num}_resized.png"))
    pdf_resized.save(os.path.join(COMPARE_DIR, f"pdf_mode_page{page_num}_resized.png"))

    # Bounding box of differences
    ys, xs = np.where(diff_mask)
    if len(ys) > 0:
        print(f"Diff bbox: x={xs.min()}-{xs.max()}, y={ys.min()}-{ys.max()}")

        # Band analysis
        print(f"\n  100px band analysis:")
        for y_start in range(0, h, 100):
            band = diff_mask[y_start:y_start+100, :]
            count = np.sum(band)
            total_band = band.size
            pct = count / total_band * 100 if total_band > 0 else 0
            if pct > 0.5:
                print(f"    y={y_start}-{y_start+100}: {pct:.2f}% diff")

                # Sample some pixels
                band_ys, band_xs = np.where(band)
                for i in range(min(3, len(band_ys))):
                    y = band_ys[i] + y_start
                    x = band_xs[i]
                    print(f"      ({x}, {y}): browser={tuple(arr_b[y, x])} pdf={tuple(arr_p[y, x])} diff={tuple(diff[y, x])}")

    # Exclude border (3px on each side)
    border_mask = np.zeros((h, w), dtype=bool)
    border_mask[:5, :] = True
    border_mask[-5:, :] = True
    border_mask[:, :5] = True
    border_mask[:, -5:] = True

    inner_diff = np.sum(diff_mask & ~border_mask)
    inner_total = total - np.sum(border_mask)
    inner_pct = inner_diff / inner_total * 100
    print(f"\n  After excluding 5px border: {inner_diff}/{inner_total} ({inner_pct:.4f}%)")

# === ELEMENT-LEVEL COMPARISON ===
print("\n" + "=" * 60)
print("ELEMENT-LEVEL COMPARISON (Browser mode vs PDF mode)")
print("=" * 60)

for sel in ALL_ELEMENTS:
    b = browser_layout.get(sel, {})
    p = pdf_layout.get(sel, {})

    if not b.get("exists") or not p.get("exists"):
        print(f"\n  {sel}: MISSING (browser={b.get('exists')}, pdf={p.get('exists')})")
        continue

    print(f"\n  {sel}:")
    br = b["rect"]
    pr = p["rect"]

    # Position comparison
    for prop in ["x", "y", "width", "height", "top", "bottom", "left", "right"]:
        bv = br.get(prop)
        pv = pr.get(prop)
        if bv is not None and pv is not None:
            diff_val = abs(bv - pv)
            match = "OK" if diff_val < 1.0 else f"DIFF ({diff_val:.1f}px)"
            if diff_val >= 1.0:
                print(f"    {prop}: browser={bv:.2f} pdf={pv:.2f} {match}")

    # Computed CSS comparison
    css_diffs = []
    for prop in COMPUTED_PROPS:
        bv = b["computed"].get(prop, "")
        pv = p["computed"].get(prop, "")
        if bv != pv:
            css_diffs.append(f"{prop}: browser='{bv}' pdf='{pv}'")

    if css_diffs:
        for d in css_diffs:
            print(f"    CSS: {d}")

    if not css_diffs and all(abs(br.get(prop, 0) - pr.get(prop, 0)) < 1.0 for prop in ["x", "y", "width", "height"]):
        print(f"    -> ALL MATCH")

# Print logo info from browser mode
print("\n" + "=" * 60)
print("LOGO INVESTIGATION")
print("=" * 60)
for img in logo_info_a:
    print(f"  src={img['src']}")
    print(f"  natural={img['naturalWidth']}x{img['naturalHeight']}")
    print(f"  rendered={img['width']}x{img['height']}")
    print(f"  complete={img['complete']}")
    print(f"  boundingRect: {img['boundingRect']}")
    print(f"  selector/class: {img['selector'] or img.get('id', 'none')}")

# Summary
print("\n" + "=" * 60)
print("CONTROLLED COMPARISON SUMMARY")
print("=" * 60)
