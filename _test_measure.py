import os
import fitz

os.chdir(os.path.dirname(os.path.abspath(__file__)))

pdf_path = r"reports\report_65.pdf"
doc = fitz.open(pdf_path)
total = doc.page_count

print(f"PDF: {os.path.basename(pdf_path)}")
print(f"Total pages: {total}")
print(f"Dimensions: {doc[0].rect.width:.1f} x {doc[0].rect.height:.1f} pt")
print()

def measure_page(page, label):
    PR = page.rect
    pw, ph = PR.width, PR.height
    print(f"\n{'='*70}")
    print(f"PAGE {label}")
    print(f"{'='*70}")
    print(f"Dimensions: {pw:.1f} x {ph:.1f} pt")

    # --- Text blocks with font info ---
    blocks = page.get_text("dict")["blocks"]

    print("\n--- IMAGE BLOCKS ---")
    for b in blocks:
        if b["type"] == 1:  # image
            x0, y0, x1, y1 = b["bbox"]
            print(f"  IMAGE: x0={x0:.1f} y0={y0:.1f} x1={x1:.1f} y1={y1:.1f} "
                  f"from_top={ph-y1:.1f}pt from_bot={y0:.1f}pt "
                  f"w={x1-x0:.1f} h={y1-y0:.1f}")

    print("\n--- DRAWINGS (lines/rects/separators) ---")
    drawings = page.get_drawings()
    for d in drawings:
        rect = d.get("rect")
        items = d.get("items", [])
        if rect and (rect.y0 < 80 or ph - rect.y1 < 80 or abs(rect.x0) < 5 or abs(rect.x1 - pw) < 5):
            # Show drawings near top/bottom/edges
            item_type = items[0][0] if items else "?"
            print(f"  Drawing[{item_type}]: rect=({rect.x0:.1f},{rect.y0:.1f})->({rect.x1:.1f},{rect.y1:.1f}) "
                  f"from_top={ph-rect.y1:.1f} from_bot={rect.y0:.1f}")

    print("\n--- TEXT SPANS (near top 80pt or bottom 80pt) ---")
    for b in blocks:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            for s in l["spans"]:
                x0, y0, x1, y1 = s["bbox"]
                ft = ph - y1
                fb = y0
                text = s["text"].strip()
                if not text:
                    continue
                if ft < 80 or fb < 80:
                    font = s.get("font", "?")
                    size = s.get("size", 0)
                    print(f"  '{text[:60]}' | font={font} size={size:.1f}pt | "
                          f"x0={x0:.1f} y0={y0:.1f} x1={x1:.1f} y1={y1:.1f} | "
                          f"from_top={ft:.1f}pt from_bot={fb:.1f}pt")

    # --- Content boundary ---
    print("\n--- CONTENT BOUNDARIES ---")
    all_spans = []
    for b in blocks:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            for s in l["spans"]:
                text = s["text"].strip()
                if text:
                    x0, y0, x1, y1 = s["bbox"]
                    ft = ph - y1
                    fb = y0
                    all_spans.append((ft, fb, text[:60], s.get("size", 0)))

    all_spans.sort(key=lambda x: x[0])

    content_start = None
    for ft, fb, text, size in all_spans:
        if ft > 60:
            content_start = (ft, text, size)
            break

    content_end = None
    for ft, fb, text, size in reversed(all_spans):
        if fb > 70:
            content_end = (fb, text, size)
            break

    print(f"  Header bottom -> Content top: ", end="")
    if content_start:
        print(f"content starts at from_top={content_start[0]:.1f}pt, text='{content_start[1]}'")
    else:
        print("NONE")

    print(f"  Content bottom -> Footer top: ", end="")
    if content_end:
        print(f"content ends at from_bot={content_end[0]:.1f}pt, text='{content_end[1]}'")
    else:
        print("NONE")

for idx in [0, 1, 2, total-1]:
    measure_page(doc[idx], idx + 1)

doc.close()
