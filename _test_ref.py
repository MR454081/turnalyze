import os, fitz
os.chdir(os.path.dirname(os.path.abspath(__file__)))

pdf_path = "reports/final_turnalyze_report.pdf"
doc = fitz.open(pdf_path)
print(f"Pages: {doc.page_count}")
print(f"Dims: {doc[0].rect.width} x {doc[0].rect.height}")

for i in [0, 1, 2, doc.page_count-1]:
    page = doc[i]
    ph = page.rect.height
    blocks = page.get_text("dict")["blocks"]
    print(f"\n--- Page {i+1} ---")
    for b in blocks:
        if b["type"] == 1:
            x0,y0,x1,y1 = b["bbox"]
            print(f"  IMG: x={x0:.1f}-{x1:.1f} from_top={ph-y1:.1f} from_bot={y0:.1f} w={x1-x0:.1f} h={y1-y0:.1f}")
    drawings = page.get_drawings()
    for d in drawings:
        r = d.get("rect")
        if r and (r.y0 < 80 or ph - r.y1 < 80):
            print(f"  DRAW: rect=({r.x0:.1f},{r.y0:.1f})->({r.x1:.1f},{r.y1:.1f}) from_top={ph-r.y1:.1f} from_bot={r.y0:.1f}")
    for b in blocks:
        if b["type"] != 0: continue
        for l in b["lines"]:
            for s in l["spans"]:
                x0,y0,x1,y1 = s["bbox"]
                ft = ph - y1
                fb = y0
                if ft < 80 or fb < 80:
                    txt = s["text"].strip()
                    if txt:
                        print(f"  TXT: \"{txt[:50]}\" font={s['font']} size={s['size']:.1f} from_top={ft:.1f} from_bot={fb:.1f}")

doc.close()
