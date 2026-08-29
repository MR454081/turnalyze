"""
Focused visual comparison: crop to content area (excluding browser border),
then compare specific regions of interest.
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageChops
import fitz

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COMPARE_DIR = os.path.join(BASE_DIR, "visual_compare")

DPI = 96
SCALE = DPI / 72.0

# Load images
browser_p1 = Image.open(os.path.join(COMPARE_DIR, "browser_page1.png")).convert("RGB")
browser_p2 = Image.open(os.path.join(COMPARE_DIR, "browser_page2.png")).convert("RGB")
pdf_doc = fitz.open(os.path.join(COMPARE_DIR, "downloaded_report.pdf"))

pdf_p1 = pdf_doc[0].get_pixmap(matrix=fitz.Matrix(SCALE, SCALE))
pdf_p1_img = Image.frombytes("RGB", [pdf_p1.width, pdf_p1.height], pdf_p1.samples)

pdf_p2 = pdf_doc[1].get_pixmap(matrix=fitz.Matrix(SCALE, SCALE))
pdf_p2_img = Image.frombytes("RGB", [pdf_p2.width, pdf_p2.height], pdf_p2.samples)

print(f"Browser P1: {browser_p1.size}, PDF P1: {pdf_p1_img.size}")
print(f"Browser P2: {browser_p2.size}, PDF P2: {pdf_p2_img.size}")

# The browser screenshot includes 1px border on each side.
# Crop to content area (1px inset).
# Browser: page element is 794x1123, border is 1px -> content is 792x1121
# PDF: full page is 794x1123 (no border)

# For fair comparison, crop browser to remove border
bw, bh = browser_p1.size
browser_p1_content = browser_p1.crop((1, 1, bw-1, bh-1))  # Remove 1px border
bw2, bh2 = browser_p2.size
browser_p2_content = browser_p2.crop((1, 1, bw2-1, bh2-1))

print(f"\nBrowser P1 content (after crop): {browser_p1_content.size}")
print(f"PDF P1: {pdf_p1_img.size}")

# Now compare. Browser content is 792x1121, PDF is 794x1123.
# Resize PDF to match browser content for pixel-exact comparison
pdf_p1_resized = pdf_p1_img.resize(browser_p1_content.size)
pdf_p2_resized = pdf_p2_img.resize(browser_p2_content.size)

def detailed_compare(browser_img, pdf_img, label, output_prefix):
    """Compare two images and produce detailed analysis."""
    bw, bh = browser_img.size
    pw, ph = pdf_img.size
    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"Browser: {bw}x{bh}, PDF: {pw}x{ph}")

    arr_b = np.array(browser_img, dtype=np.int16)
    arr_p = np.array(pdf_img, dtype=np.int16)

    diff = np.abs(arr_b - arr_p)
    diff_mag = np.mean(diff, axis=2)
    diff_mask = diff_mag > 20

    total = bw * bh
    diff_count = np.sum(diff_mask)
    diff_pct = diff_count / total * 100

    print(f"Differing pixels (>20 threshold): {diff_count}/{total} ({diff_pct:.4f}%)")

    if diff_pct < 0.05:
        print("  -> Essentially identical (only font anti-aliasing)")
        return

    # Create diff visualization
    diff_img = np.zeros((bh, bw, 3), dtype=np.uint8)
    diff_img[diff_mask] = [255, 0, 0]  # Red for differences
    diff_pil = Image.fromarray(diff_img)
    # Blend with browser image at 30% opacity
    blended = Image.blend(browser_img, diff_pil, alpha=0.3)
    blended.save(os.path.join(COMPARE_DIR, f"{output_prefix}_diff_overlay.png"))
    print(f"  Diff overlay saved: {output_prefix}_diff_overlay.png")

    # Analyze regions
    # Split page into horizontal bands of 100px
    print(f"\n  Band analysis (100px bands):")
    for y_start in range(0, bh, 100):
        band = diff_mask[y_start:y_start+100, :]
        count = np.sum(band)
        total_band = band.size
        pct = count / total_band * 100 if total_band > 0 else 0
        if pct > 0.1:
            # Get bounding box of differences
            cols = np.any(band, axis=0)
            rows = np.any(band, axis=1)
            if np.any(cols):
                x_min = np.argmax(cols)
                x_max = len(cols) - np.argmax(cols[::-1]) - 1
                y_min = np.argmax(rows)
                y_max = len(rows) - np.argmax(rows[::-1]) - 1
                print(f"    y={y_start}-{y_start+100}: {pct:.2f}% diff, bbox: x={x_min}-{x_max}, y={y_min}-{y_max}")

                # Sample some pixels
                ys, xs = np.where(diff_mask[y_start:y_start+100, :])
                if len(ys) > 0:
                    for i in range(min(3, len(ys))):
                        y = ys[i] + y_start
                        x = xs[i]
                        b_pixel = tuple(arr_b[y, x])
                        p_pixel = tuple(arr_p[y, x])
                        d = tuple(diff[y, x])
                        print(f"      ({x}, {y}): browser={b_pixel} pdf={p_pixel} diff={d}")

    # Check for color differences (not just brightness)
    # Compute mean color difference by channel
    mean_diff_r = np.mean(diff[:, :, 0][diff_mask])
    mean_diff_g = np.mean(diff[:, :, 1][diff_mask])
    mean_diff_b = np.mean(diff[:, :, 2][diff_mask])
    print(f"\n  Mean channel differences: R={mean_diff_r:.1f} G={mean_diff_g:.1f} B={mean_diff_b:.1f}")

    # Check if differences are mostly blue channel (text rendering)
    blue_dominant = np.sum(diff_mask & (diff[:,:,2] > diff[:,:,0]) & (diff[:,:,2] > diff[:,:,1]))
    print(f"  Blue-dominant differences: {blue_dominant} ({blue_dominant/max(diff_count,1)*100:.1f}%)")

    # Check if differences are at text areas (vertical strips around x=45-760 for cover page)
    text_region = diff_mask[100:1100, 50:745] if label == "PAGE 1" else diff_mask[100:1100, 50:745]
    text_diff = np.sum(text_region)
    text_total = text_region.size
    print(f"  Text region (x=50-745, y=100-1100): {text_diff}/{text_total} ({text_diff/max(text_total,1)*100:.2f}%)")

    # Also save side-by-side comparison
    side_by_side = Image.new("RGB", (bw + pw + 20, max(bh, ph)), (128, 128, 128))
    side_by_side.paste(browser_img, (0, 0))
    side_by_side.paste(pdf_img, (bw + 20, 0))
    side_by_side.save(os.path.join(COMPARE_DIR, f"{output_prefix}_side_by_side.png"))
    print(f"  Side-by-side saved: {output_prefix}_side_by_side.png")

# Compare Page 1
detailed_compare(browser_p1_content, pdf_p1_resized, "PAGE 1 (Cover)", "page1")

# Compare Page 2
detailed_compare(browser_p2_content, pdf_p2_resized, "PAGE 2 (Overview)", "page2")

pdf_doc.close()

# Also create a combined diff image
print("\n=== Creating final comparison images ===")

# Side-by-side all
browser_combined = Image.new("RGB", (794, 2246), (255, 255, 255))
browser_combined.paste(browser_p1, (0, 0))
browser_combined.paste(browser_p2, (0, 1123))
browser_combined.save(os.path.join(COMPARE_DIR, "browser_combined.png"))

pdf_combined = Image.new("RGB", (794, 2246), (255, 255, 255))
pdf_combined.paste(pdf_p1_img, (0, 0))
pdf_combined.paste(pdf_p2_img, (0, 1123))
pdf_combined.save(os.path.join(COMPARE_DIR, "pdf_combined.png"))

# Diff of combined
browser_combined.resize((794, 2246))
pdf_resized = pdf_combined.resize((794, 2246))
diff_combined = ImageChops.difference(browser_combined, pdf_resized)
diff_combined.save(os.path.join(COMPARE_DIR, "combined_diff.png"))

print(f"Files saved to: {COMPARE_DIR}")
print("Done.")
