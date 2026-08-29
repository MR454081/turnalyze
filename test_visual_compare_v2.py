"""
Visual comparison: Browser HTML Page 1/2 vs Downloaded PDF Page 1/2.
Fixed: taller viewport, proper clipping, detailed diff analysis.
"""
import os
import sys
from playwright.sync_api import sync_playwright
import fitz
from PIL import Image
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_PDF = os.path.join(BASE_DIR, "static", "pdfs", "Analysis_report.pdf")
COMPARE_DIR = os.path.join(BASE_DIR, "visual_compare")
os.makedirs(COMPARE_DIR, exist_ok=True)

DPI = 96
SCALE = DPI / 72.0  # 1.333

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=[
        "--allow-file-access-from-files",
        "--disable-web-security",
    ])
    context = browser.new_context(
        viewport={"width": 1280, "height": 4000},  # Tall enough for both pages
        device_scale_factor=1,
    )
    page = context.new_page()

    # Login
    print("=== Login ===")
    page.goto("http://127.0.0.1:5000/", wait_until="networkidle")
    page.fill('input[name="email"]", "admin@turnalyze.com")' if False else 'input[name="email"]', "admin@turnalyze.com")
    page.fill('input[name="password"]', "admin123")
    page.click('form button[type="submit"]')
    page.wait_for_timeout(2000)

    # Upload
    print("\n=== Upload ===")
    page.goto("http://127.0.0.1:5000/upload", wait_until="networkidle")
    page.set_input_files('#fileInput', SOURCE_PDF)
    with page.expect_navigation(wait_until="load", timeout=180000):
        page.click('.analyze-btn')
    page.wait_for_timeout(5000)

    # Download PDF
    print("\n=== Download PDF ===")
    report_id = page.evaluate("() => document.getElementById('report-meta')?.dataset.reportId || ''")
    with page.expect_download(timeout=60000) as dl_info:
        page.click('.report-download-button')
    pdf_path = os.path.join(COMPARE_DIR, "downloaded_report.pdf")
    dl_info.value.save_as(pdf_path)
    print(f"Downloaded: {pdf_path} ({os.path.getsize(pdf_path)} bytes)")

    doc = fitz.open(pdf_path)
    print(f"PDF pages: {doc.page_count}")

    # Screenshot Page 1 (cover) - full page element including border
    cover_rect = page.evaluate("""
        () => {
            const r = document.querySelector(".cover-page").getBoundingClientRect();
            return {x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height)};
        }
    """)
    print(f"\nCover rect: {cover_rect}")
    browser_p1_path = os.path.join(COMPARE_DIR, "browser_page1.png")
    page.screenshot(path=browser_p1_path, clip=cover_rect, scale="css")

    # Screenshot Page 2 (overview) - full page element including border
    overview_rect = page.evaluate("""
        () => {
            const r = document.querySelector(".overview-page").getBoundingClientRect();
            return {x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height)};
        }
    """)
    print(f"Overview rect: {overview_rect}")
    browser_p2_path = os.path.join(COMPARE_DIR, "browser_page2.png")
    page.screenshot(path=browser_p2_path, clip=overview_rect, scale="css")

    # Render PDF pages at 96 DPI
    print("\n=== Render PDF pages ===")
    pdf_p1 = render_pdf_page = fitz.open(pdf_path)[0].get_pixmap(matrix=fitz.Matrix(SCALE, SCALE))
    pdf_p1_img = Image.frombytes("RGB", [pdf_p1.width, pdf_p1.height], pdf_p1.samples)
    pdf_p1_path = os.path.join(COMPARE_DIR, "pdf_page1.png")
    pdf_p1_img.save(pdf_p1_path)
    print(f"PDF Page 1: {pdf_p1_path} ({pdf_p1_img.width}x{pdf_p1_img.height})")

    pdf_p2 = fitz.open(pdf_path)[1].get_pixmap(matrix=fitz.Matrix(SCALE, SCALE))
    pdf_p2_img = Image.frombytes("RGB", [pdf_p2.width, pdf_p2.height], pdf_p2.samples)
    pdf_p2_path = os.path.join(COMPARE_DIR, "pdf_page2.png")
    pdf_p2_img.save(pdf_p2_path)
    print(f"PDF Page 2: {pdf_p2_path} ({pdf_p2_img.width}x{pdf_p2_img.height})")

    browser_img_p1 = Image.open(browser_p1_path)
    browser_img_p2 = Image.open(browser_p2_path)

    # Now compare each page
    for page_num in [1, 2]:
        print(f"\n{'='*60}")
        print(f"PAGE {page_num} VISUAL COMPARISON")
        print(f"{'='*60}")

        if page_num == 1:
            browser_img = browser_img_p1
            pdf_img = pdf_p1_img
        else:
            browser_img = browser_img_p2
            pdf_img = pdf_p2_img

        bw, bh = browser_img.size
        pw, ph = pdf_img.size
        print(f"Browser: {bw}x{bh}")
        print(f"PDF:     {pw}x{ph}")

        # Resize PDF to match browser dimensions (they should be very close)
        # Both are A4 at 96 DPI = 794x1123
        w = min(bw, pw)
        h = min(bh, ph)
        browser_resized = browser_img.resize((w, h)).convert("RGB")
        pdf_resized = pdf_img.resize((w, h)).convert("RGB")

        arr_b = np.array(browser_resized, dtype=np.int16)
        arr_p = np.array(pdf_resized, dtype=np.int16)

        diff = np.abs(arr_b - arr_p)
        diff_mag = np.mean(diff, axis=2)
        diff_mask = diff_mag > 20  # Threshold for significant difference

        total = w * h
        diff_count = np.sum(diff_mask)
        diff_pct = diff_count / total * 100

        print(f"Dimensions: {w}x{h}")
        print(f"Differing pixels (>20 threshold): {diff_count}/{total} ({diff_pct:.2f}%)")

        # Analyze WHERE differences are
        # The browser page has a 1px border and subtle shadow
        # The border is at the very edge of the element

        # Check the outer border region (1px on each side for border, plus shadow)
        border_region = np.zeros((h, w), dtype=bool)
        border_region[0:3, :] = True  # Top 3px (border + shadow)
        border_region[-3:, :] = True  # Bottom 3px
        border_region[:, 0:3] = True  # Left 3px
        border_region[:, -3:] = True  # Right 3px

        border_diff = np.sum(diff_mask & border_region)
        border_total = np.sum(border_region)
        inner_diff = np.sum(diff_mask & ~border_region)
        inner_total = total - border_total

        print(f"Border/shadow region: {border_diff}/{border_total} ({border_diff/max(border_total,1)*100:.2f}%)")
        print(f"Inner content:        {inner_diff}/{inner_total} ({inner_diff/max(inner_total,1)*100:.2f}%)")

        if inner_diff / max(inner_total, 1) * 100 > 0.5:
            print("  >>> INNER CONTENT HAS DIFFERENCES <<<")

            # Detailed region analysis
            # Divide into horizontal bands to identify which sections differ
            band_height = 100
            print(f"\n  Horizontal band analysis (threshold=20, band height={band_height}px):")
            for by in range(0, h, band_height):
                band = diff_mask[by:by+band_height, :]
                count = np.sum(band)
                total_band = band.size
                pct = count / total_band * 100 if total_band > 0 else 0
                if pct > 0.5:
                    print(f"    y={by}-{by+band_height}: {count}/{total_band} ({pct:.2f}%) differing")

                    # Sample some differing pixels in this band
                    ys, xs = np.where(band)
                    if len(ys) > 0:
                        for i in range(min(3, len(ys))):
                            y = ys[i] + by
                            x = xs[i]
                            b_pixel = browser_resized.getpixel((x, y))
                            p_pixel = pdf_resized.getpixel((x, y))
                            d = diff[y, x]
                            print(f"      ({x}, {y}): B={b_pixel} P={p_pixel} diff={d.tolist()}")

            # Check for blue color differences (logo colors)
            # The Turnalyze/turnitin logo has blue colors
            b_blue = arr_b[:,:,2].astype(float)
            b_red = arr_b[:,:,0].astype(float)
            b_green = arr_b[:,:,1].astype(float)
            p_blue = arr_p[:,:,2].astype(float)
            p_red = arr_p[:,:,0].astype(float)
            p_green = arr_p[:,:,1].astype(float)

            # Check if logo area (top-left of cover page) has blue in one but not other
            if page_num == 1:
                logo_area_b = b_blue[10:60, 10:80] - b_red[10:60, 10:80]
                logo_area_p = p_blue[10:60, 10:80] - p_red[10:60, 10:80]
                b_has_blue = np.sum(logo_area_b > 50)
                p_has_blue = np.sum(logo_area_p > 50)
                print(f"\n  Logo area blue pixels: browser={b_has_blue}, pdf={p_has_blue}")
                if b_has_blue == 0 and p_has_blue > 0:
                    print("  >>> Browser missing logo (blue) in logo area <<<")
                elif b_has_blue > 0 and p_has_blue == 0:
                    print("  >>> PDF missing logo (blue) in logo area <<<")
                elif b_has_blue > 0 and p_has_blue > 0:
                    print("  >>> Both have logo <<<")
        elif diff_pct < 0.5:
            print("  Content matches (only border/shadow differences)")
        elif diff_pct < 2:
            print("  Minor differences (likely font anti-aliasing)")
        else:
            print(f"  Significant differences: {diff_pct:.2f}%")

    doc.close()
    browser.close()
    print(f"\nAll images saved to: {COMPARE_DIR}")
