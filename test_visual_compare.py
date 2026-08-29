"""
Visual comparison: Browser HTML Page 1/2 vs Downloaded PDF Page 1/2.
Uses Playwright for browser screenshots, PyMuPDF for PDF rendering,
and PIL+numpy for pixel-level comparison.
"""
import os
import time
import io
from playwright.sync_api import sync_playwright
import fitz
from PIL import Image
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_PDF = os.path.join(BASE_DIR, "static", "pdfs", "Analysis_report.pdf")
COMPARE_DIR = os.path.join(BASE_DIR, "visual_compare")
os.makedirs(COMPARE_DIR, exist_ok=True)

DPI = 96  # CSS pixel density for 1:1 comparison
SCALE = DPI / 72.0  # PyMuPDF matrix scale factor

def render_pdf_page(pdf_path, page_num, scale=SCALE):
    """Render a PDF page as a PIL Image at the given DPI."""
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img

def images_match(img1, img2, threshold=10):
    """Compare two images pixel by pixel, return diff image and stats."""
    # Resize to same dimensions
    w = min(img1.width, img2.width)
    h = min(img1.height, img2.height)
    img1_resized = img1.resize((w, h)).convert("RGB")
    img2_resized = img2.resize((w, h)).convert("RGB")

    arr1 = np.array(img1_resized, dtype=np.int16)
    arr2 = np.array(img2_resized, dtype=np.int16)

    diff = np.abs(arr1 - arr2)
    diff_magnitude = np.mean(diff, axis=2)  # Average RGB difference per pixel

    # Pixels that differ by more than threshold
    differing = diff_magnitude > threshold
    diff_count = np.sum(differing)
    total_pixels = w * h
    diff_pct = (diff_count / total_pixels) * 100

    # Create diff image (red for differences)
    diff_img = np.zeros((h, w, 3), dtype=np.uint8)
    diff_img[:, :, 0] = 255 * differing  # Red where different

    # Overlay: show diff areas in red on a copy of img1
    overlay = arr1.astype(np.uint8).copy()
    overlay[differing] = [255, 0, 0]  # Red where different

    return Image.fromarray(overlay), diff_pct, diff_count, total_pixels


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=[
        "--allow-file-access-from-files",
        "--disable-web-security",
    ])
    context = browser.new_context(
        viewport={"width": 1280, "height": 1800},
        device_scale_factor=1,
    )
    page = context.new_page()

    # 1. Login
    print("=== Logging in ===")
    page.goto("http://127.0.0.1:5000/", wait_until="networkidle")
    page.fill('input[name="email"]', "admin@turnalyze.com")
    page.fill('input[name="password"]', "admin123")
    page.click('form button[type="submit"]')
    page.wait_for_timeout(2000)
    print(f"Login URL: {page.url}")

    # 2. Upload
    print("\n=== Uploading PDF ===")
    page.goto("http://127.0.0.1:5000/upload", wait_until="networkidle")
    page.set_input_files('#fileInput', SOURCE_PDF)
    with page.expect_navigation(wait_until="load", timeout=180000):
        page.click('.analyze-btn')
    page.wait_for_timeout(5000)

    has_cover = page.evaluate("() => !!document.querySelector('.cover-page')")
    print(f"Has cover-page: {has_cover}")

    if not has_cover:
        print("ERROR: Report page not loaded")
        browser.close()
        exit(1)

    # 3. Screenshot browser Page 1 (cover)
    print("\n=== Capturing browser screenshots ===")
    cover_rect = page.evaluate("""
        () => {
            const r = document.querySelector(".cover-page").getBoundingClientRect();
            return {x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height)};
        }
    """)
    print(f"Cover page rect: {cover_rect}")

    cover_screenshot = os.path.join(COMPARE_DIR, "browser_page1.png")
    page.screenshot(path=cover_screenshot, clip=cover_rect, scale="css")
    print(f"Browser Page 1: {cover_screenshot} ({cover_rect['width']}x{cover_rect['height']})")

    # Screenshot overview page
    overview_rect = page.evaluate("""
        () => {
            const r = document.querySelector(".overview-page").getBoundingClientRect();
            return {x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height)};
        }
    """)
    overview_screenshot = os.path.join(COMPARE_DIR, "browser_page2.png")
    page.screenshot(path=overview_screenshot, clip=overview_rect, scale="css")
    print(f"Browser Page 2: {overview_screenshot} ({overview_rect['width']}x{overview_rect['height']})")

    # 4. Download PDF
    print("\n=== Downloading PDF ===")
    report_id = page.evaluate("() => document.getElementById('report-meta')?.dataset.reportId || ''")
    print(f"Report ID: {report_id}")

    # Remove download bar first (it would block the screenshot)
    with page.expect_download(timeout=60000) as dl_info:
        page.click('.report-download-button')
    download = dl_info.value
    pdf_path = os.path.join(COMPARE_DIR, "downloaded_report.pdf")
    download.save_as(pdf_path)
    print(f"PDF downloaded: {pdf_path}")
    print(f"PDF size: {os.path.getsize(pdf_path)} bytes")

    # 5. Check PDF
    doc = fitz.open(pdf_path)
    print(f"PDF pages: {doc.page_count}")
    src_doc = fitz.open(SOURCE_PDF)
    print(f"Expected: {src_doc.page_count + 2}")
    src_doc.close()

    # 6. Render PDF pages as images
    print("\n=== Rendering PDF pages ===")
    # Use the same scale as the browser screenshot
    # Browser uses device_scale_factor=1 with scale="2d" in screenshot
    # So 1 CSS px = 2 device pixels in the screenshot
    # PDF at 96*2/72 = 2.667 DPI matrix gives similar resolution
    pdf_scale = DPI / 72.0  # 1.333 for 96 DPI

    pdf_page1 = render_pdf_page(pdf_path, 0, scale=pdf_scale)
    pdf_page1_path = os.path.join(COMPARE_DIR, "pdf_page1.png")
    pdf_page1.save(pdf_page1_path)
    print(f"PDF Page 1 image: {pdf_page1_path} ({pdf_page1.width}x{pdf_page1.height})")

    pdf_page2 = render_pdf_page(pdf_path, 1, scale=pdf_scale)
    pdf_page2_path = os.path.join(COMPARE_DIR, "pdf_page2.png")
    pdf_page2.save(pdf_page2_path)
    print(f"PDF Page 2 image: {pdf_page2_path} ({pdf_page2.width}x{pdf_page2.height})")

    doc.close()

    # 7. Load browser screenshots and compare
    print("\n=== VISUAL COMPARISON ===")

    browser_p1 = Image.open(cover_screenshot)
    browser_p2 = Image.open(overview_screenshot)

    # Also save browser screenshots at 1:1 for inspection
    browser_p1.save(os.path.join(COMPARE_DIR, "browser_page1_full.png"))
    browser_p2.save(os.path.join(COMPARE_DIR, "browser_page2_full.png"))

    # Compare Page 1
    print("\n--- PAGE 1 (Cover) ---")
    print(f"Browser screenshot: {browser_p1.width}x{browser_p1.height}")
    print(f"PDF render:         {pdf_page1.width}x{pdf_page1.height}")

    diff_p1, pct_p1, count_p1, total_p1 = images_match(browser_p1, pdf_page1, threshold=15)
    diff_p1.save(os.path.join(COMPARE_DIR, "diff_page1.png"))
    print(f"  Differing pixels: {count_p1}/{total_p1} ({pct_p1:.2f}%)")

    # Analyze where differences are
    if pct_p1 > 0.1:
        # Check if differences are at edges (borders/shadows)
        arr_browser = np.array(browser_p1.resize((min(browser_p1.width, pdf_page1.width),
                                                   min(browser_p1.height, pdf_page1.height))).convert("RGB"))
        arr_pdf = np.array(pdf_page1.resize(arr_browser.shape[:2][::-1]).convert("RGB"))
        diff_arr = np.abs(arr_browser.astype(int) - arr_pdf.astype(int))
        diff_mag = np.mean(diff_arr, axis=2)
        diff_mask = diff_mag > 15

        # Check percentage of differences in the outer 10px border
        h, w = diff_mask.shape
        outer_ring = np.zeros((h, w), dtype=bool)
        outer_ring[:10, :] = True
        outer_ring[-10:, :] = True
        outer_ring[:, :10] = True
        outer_ring[:, -10:] = True

        outer_diff = np.sum(diff_mask & outer_ring)
        outer_total = np.sum(outer_ring)
        inner_diff = np.sum(diff_mask & ~outer_ring)
        inner_total = total_p1 - outer_total

        print(f"  Outer 10px ring: {outer_diff}/{outer_total} differing pixels ({outer_diff/max(outer_total,1)*100:.2f}%)")
        print(f"  Inner content:   {inner_diff}/{inner_total} differing pixels ({inner_diff/max(inner_total,1)*100:.2f}%)")

        if inner_diff / max(inner_total, 1) * 100 < 0.5:
            print("  -> Content within page matches (differences are border/shadow only)")
        else:
            print("  -> Content within page has differences!")

        # Sample some differing inner pixels
        inner_diffs = np.argwhere(diff_mask & ~outer_ring)
        if len(inner_diffs) > 0:
            print(f"  Sample differing inner pixel locations (first 5):")
            for i, (y, x) in enumerate(inner_diffs[:5]):
                print(f"    ({x}, {y}): browser={arr_browser[y,x].tolist()} pdf={arr_pdf[y,x].tolist()} diff={diff_arr[y,x].tolist()}")

    # Compare Page 2
    print("\n--- PAGE 2 (Overview) ---")
    print(f"Browser screenshot: {browser_p2.width}x{browser_p2.height}")
    print(f"PDF render:         {pdf_page2.width}x{pdf_page2.height}")

    diff_p2, pct_p2, count_p2, total_p2 = images_match(browser_p2, pdf_page2, threshold=15)
    diff_p2.save(os.path.join(COMPARE_DIR, "diff_page2.png"))
    print(f"  Differing pixels: {count_p2}/{total_p2} ({pct_p2:.2f}%)")

    if pct_p2 > 0.1:
        arr_browser = np.array(browser_p2.resize((min(browser_p2.width, pdf_page2.width),
                                                   min(browser_p2.height, pdf_page2.height))).convert("RGB"))
        arr_pdf = np.array(pdf_page2.resize(arr_browser.shape[:2][::-1]).convert("RGB"))
        diff_arr = np.abs(arr_browser.astype(int) - arr_pdf.astype(int))
        diff_mag = np.mean(diff_arr, axis=2)
        diff_mask = diff_mag > 15

        h, w = diff_mask.shape
        outer_ring = np.zeros((h, w), dtype=bool)
        outer_ring[:10, :] = True
        outer_ring[-10:, :] = True
        outer_ring[:, :10] = True
        outer_ring[:, -10:] = True

        outer_diff = np.sum(diff_mask & outer_ring)
        outer_total = np.sum(outer_ring)
        inner_diff = np.sum(diff_mask & ~outer_ring)
        inner_total = total_p2 - outer_total

        print(f"  Outer 10px ring: {outer_diff}/{outer_total} differing pixels ({outer_diff/max(outer_total,1)*100:.2f}%)")
        print(f"  Inner content:   {inner_diff}/{inner_total} differing pixels ({inner_diff/max(inner_total,1)*100:.2f}%)")

        if inner_diff / max(inner_total, 1) * 100 < 0.5:
            print("  -> Content within page matches (differences are border/shadow only)")
        else:
            print("  -> Content within page has differences!")

        inner_diffs = np.argwhere(diff_mask & ~outer_ring)
        if len(inner_diffs) > 0:
            print(f"  Sample differing inner pixel locations (first 10):")
            for i, (y, x) in enumerate(inner_diffs[:10]):
                print(f"    ({x}, {y}): browser={arr_browser[y,x].tolist()} pdf={arr_pdf[y,x].tolist()} diff={diff_arr[y,x].tolist()}")

    print("\n=== Summary ===")
    print(f"Page 1 - Total diff: {pct_p1:.2f}%, Inner content diff: {inner_diff/max(inner_total,1)*100:.2f}%")
    print(f"Page 2 - Total diff: {pct_p2:.2f}%, Inner content diff: {inner_diff/max(inner_total,1)*100:.2f}%")

    if pct_p1 < 0.5 and pct_p2 < 0.5:
        print("\nBrowser HTML and PDF Page 1/2 visually match.")
    else:
        print(f"\nPage 1 diff: {pct_p1:.2f}%, Page 2 diff: {pct_p2:.2f}%")

    browser.close()
    print(f"\nAll images saved to: {COMPARE_DIR}")
