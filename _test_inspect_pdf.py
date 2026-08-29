import os
import fitz
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Try report 65 first
pdf_path = r"C:\Users\raham\OneDrive\Desktop\turnalyze (4)\turnalyze (2)\turnalyze\reports\report_65.pdf"

if not os.path.isfile(pdf_path):
    print(f"File not found: {pdf_path}")
    # Try other reports
    import glob
    pdfs = sorted(glob.glob(r"C:\Users\raham\OneDrive\Desktop\turnalyze (4)\turnalyze (2)\turnalyze\reports\report_*.pdf"))
    for p in pdfs:
        if "highlighted" not in p:
            doc = fitz.open(p)
            pw, ph = doc[0].rect.width, doc[0].rect.height
            print(f"  {os.path.basename(p)}: {pw:.0f}x{ph:.0f}pt, {doc.page_count} pages")
            doc.close()
    sys.exit(1)

doc = fitz.open(pdf_path)
total = doc.page_count
pw0, ph0 = doc[0].rect.width, doc[0].rect.height
print(f"PDF: {os.path.basename(pdf_path)}")
print(f"Total pages: {total}")
print(f"Dimensions: {pw0:.1f} x {ph0:.1f} pt")

for i in range(min(total, 8)):
    page = doc[i]
    PR = page.rect
    pw, ph = PR.width, PR.height
    print(f"\n=== Page {i+1} (index {i}) ===")
    
    # Search for key header text patterns
    patterns = ["Page", "Submission", "Cover", "Overview", "Original", "AI Writing", "Submission ID"]
    for pattern in patterns:
        instances = page.search_for(pattern)
        for r in instances[:3]:
            from_top = ph - r.y1
            from_bottom = r.y0
            print(f"  '{pattern}' rect: x0={r.x0:.1f} x1={r.x1:.1f} top={from_top:.1f}pt bottom={from_bottom:.1f}pt h={r.y1-r.y0:.1f}pt")
    
    # Draw all text blocks and show those near top/bottom
    text_instances = page.get_text("words")
    top_words = [w for w in text_instances if (ph - w[3]) < 80]
    print(f"  Words near top (within 80pt): {len(top_words)}")
    for w in sorted(top_words, key=lambda x: -x[3])[:12]:
        from_top = ph - w[3]
        print(f"    '{w[4]}' at x={w[0]:.1f}, from_top={from_top:.1f}pt, font_size~{(w[3]-w[1]):.1f}pt")
    
    bottom_words = [w for w in text_instances if w[1] < 80]
    print(f"  Words near bottom (within 80pt): {len(bottom_words)}")
    for w in sorted(bottom_words, key=lambda x: x[1])[:12]:
        from_bottom = w[1]
        print(f"    '{w[4]}' at x={w[0]:.1f}, from_bottom={from_bottom:.1f}pt")

# Also check last page
if total > 8:
    i = total - 1
    page = doc[i]
    ph = page.rect.height
    print(f"\n=== Page {i+1} (last) ===")
    patterns = ["Page", "Submission", "Overview", "Original"]
    for pattern in patterns:
        instances = page.search_for(pattern)
        for r in instances[:3]:
            from_top = ph - r.y1
            from_bottom = r.y0
            print(f"  '{pattern}' rect: x0={r.x0:.1f} top={from_top:.1f}pt bottom={from_bottom:.1f}pt h={r.y1-r.y0:.1f}pt")

doc.close()
