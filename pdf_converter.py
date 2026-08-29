# pdf_converter.py

import os
import re
import shutil
import fitz

try:
    import pythoncom
except ImportError:
    pythoncom = None

try:
    from docx2pdf import convert
except Exception:
    convert = None


AI_HIGHLIGHT_COLOR = (
    201 / 255,
    237 / 255,
    244 / 255,
)


def convert_docx_to_pdf(docx_path):
    pdf_dir = os.path.join("static", "pdfs")
    os.makedirs(pdf_dir, exist_ok=True)
    filename = os.path.splitext(os.path.basename(docx_path))[0]
    pdf_path = os.path.join(pdf_dir, filename + ".pdf")

    if convert is None:
        raise RuntimeError("docx2pdf is not available")

    if pythoncom is None:
        raise RuntimeError(
            "pythoncom is not available; docx-to-pdf conversion requires Windows with pywin32 installed"
        )

    pythoncom.CoInitialize()
    try:
        convert(docx_path, pdf_path)
    finally:
        pythoncom.CoUninitialize()

    return pdf_path


def get_pdf_page_count(pdf_path):
    if not os.path.exists(pdf_path):
        return 0
    doc = fitz.open(pdf_path)
    count = len(doc)
    doc.close()
    return count


def extract_pdf_text(pdf_path):
    doc = fitz.open(pdf_path)
    text_parts = []
    for page in doc:
        text_parts.append(page.get_text("text"))
    doc.close()
    return "\n".join(part for part in text_parts if part)


def extract_pdf_text_regions(pdf_path):
    doc = fitz.open(pdf_path)
    regions = []
    for page_number, page in enumerate(doc):
        blocks = page.get_text("blocks")
        for block in blocks:
            text = (block[4] if len(block) > 4 else "").strip()
            if not text:
                continue
            regions.append({
                "page": page_number,
                "text": text,
                "rect": fitz.Rect(block[:4]),
            })
    doc.close()
    return regions


def _search_segment_on_page(page, segment_text):
    rects = page.search_for(segment_text)
    if rects:
        return rects

    # Clean multi-space and linebreaks
    clean_text = re.sub(r"\s+", " ", segment_text).strip()
    if clean_text != segment_text:
        rects = page.search_for(clean_text)
        if rects:
            return rects

    # Sub-phrase search for long sentences
    words = clean_text.split()
    if len(words) >= 5:
        sub_rects = []
        step = 4
        chunk_len = 6
        for i in range(0, len(words), step):
            sub_phrase = " ".join(words[i : i + chunk_len])
            if len(sub_phrase) >= 12:
                res = page.search_for(sub_phrase)
                if res:
                    sub_rects.extend(res)
        if sub_rects:
            # Deduplicate rectangles
            unique_rects = []
            for r in sub_rects:
                if not any(r.intersects(existing) and abs(r.x0 - existing.x0) < 5 for existing in unique_rects):
                    unique_rects.append(r)
            return unique_rects

    # Word-sequence fallback search
    words_data = page.get_text("words")
    if words_data and len(words) >= 3:
        target_norm = [re.sub(r"[^\w]", "", w.lower()) for w in words if re.sub(r"[^\w]", "", w.lower())]
        if target_norm:
            page_words_norm = [(w, re.sub(r"[^\w]", "", w[4].lower())) for w in words_data]
            page_tokens = [p[1] for p in page_words_norm]

            t_len = len(target_norm)
            matched_words = []
            for i in range(len(page_tokens) - t_len + 1):
                window = page_tokens[i : i + t_len]
                match_count = sum(1 for a, b in zip(window, target_norm) if a == b and a != "")
                if match_count / float(t_len) >= 0.75:
                    matched_words = [words_data[j] for j in range(i, i + t_len)]
                    break

            if matched_words:
                line_groups = {}
                for w in matched_words:
                    line_no = (w[5], w[6])
                    rect = fitz.Rect(w[0], w[1], w[2], w[3])
                    if line_no not in line_groups:
                        line_groups[line_no] = rect
                    else:
                        line_groups[line_no].include_rect(rect)
                return list(line_groups.values())

    return []


def highlight_pdf_text(source_pdf_path, output_pdf_path, ai_score=0, highlight_texts=None, text_content=None, segments=None):
    if not os.path.exists(source_pdf_path):
        raise FileNotFoundError(source_pdf_path)

    ai_segments = []
    if segments and isinstance(segments, list):
        for seg in segments:
            if isinstance(seg, dict) and seg.get("is_ai") and seg.get("text"):
                ai_segments.append(str(seg["text"]).strip())
            elif isinstance(seg, str) and seg.strip():
                ai_segments.append(seg.strip())
    elif highlight_texts:
        if isinstance(highlight_texts, (list, tuple, set)):
            ai_segments.extend([str(item).strip() for item in highlight_texts if str(item).strip()])
        else:
            ai_segments.append(str(highlight_texts).strip())

    # Deduplicate segments
    unique_segments = []
    for seg in ai_segments:
        if seg and seg not in unique_segments:
            unique_segments.append(seg)
    ai_segments = unique_segments

    print("AI segments:", len(segments) if segments else len(ai_segments))
    print("AI segments classified AI:", len(ai_segments))
    print("Highlight source:", source_pdf_path)
    print("Highlight output:", output_pdf_path)

    doc = fitz.open(source_pdf_path)
    matched_count = 0
    unmatched_count = 0

    for segment_text in ai_segments:
        segment_matched = False
        for page in doc:
            rects = _search_segment_on_page(page, segment_text)
            if rects:
                segment_matched = True
                for rect in rects:
                    # 1. Draw transparent light-cyan background rectangle behind text layer
                    page.draw_rect(rect, color=None, fill=AI_HIGHLIGHT_COLOR, overlay=False)

                    # 2. Add real PDF highlight annotation
                    annot = page.add_highlight_annot(rect)
                    if annot:
                        annot.set_colors(stroke=AI_HIGHLIGHT_COLOR)
                        annot.update()

        if segment_matched:
            matched_count += 1
        else:
            unmatched_count += 1

    print("Matched AI segments:", matched_count)
    print("Unmatched AI segments:", unmatched_count)

    if len(ai_segments) > 0 and matched_count == 0:
        print("WARNING: Detector returned AI segments, but zero matches were highlighted in the PDF!")

    output_dir = os.path.dirname(output_pdf_path) or "."
    os.makedirs(output_dir, exist_ok=True)
    doc.save(output_pdf_path)
    doc.close()
    return output_pdf_path


# =========================================================
# HEADER / FOOTER DECORATION
# =========================================================

LETTER_W = 612.0
LETTER_H = 792.0
HEADER_FOOTER_MARGIN = 45.0
HEADER_FOOTER_FONTSIZE = 6.5
HEADER_FOOTER_COLOR = (0.4, 0.4, 0.4)
HEADER_FOOTER_LINE_COLOR = (0.85, 0.85, 0.85)

LOGO_ASPECT = 295.0 / 960.0
LOGO_W = 45.0
LOGO_H = LOGO_W * LOGO_ASPECT


def _hf_text_width(text, fontsize=HEADER_FOOTER_FONTSIZE):
    font = fitz.Font("helv")
    return font.text_length(text, fontsize=fontsize)


def apply_header_footer(
    page,
    page_number,
    total_pages,
    page_title,
    submission_id,
    logo_path,
):
    """
    Apply a native PDF header and footer to a single page using PyMuPDF
    drawing operations.

    Preserves all existing page content: text remains selectable and
    searchable.  No rasterization is performed.
    """
    PW = page.rect.width
    PH = page.rect.height

    ml = HEADER_FOOTER_MARGIN
    mr_x = PW - HEADER_FOOTER_MARGIN

    page.draw_rect(
        fitz.Rect(0.5, 0.5, PW - 0.5, PH - 0.5),
        color=HEADER_FOOTER_LINE_COLOR,
        width=0.5,
        overlay=True,
    )

    h_top = PH - 18.0
    h_bot = h_top + LOGO_H
    h_base = h_top + 12.0

    f_top = 6.0
    f_bot = f_top + LOGO_H
    f_base = f_top + 12.0

    if logo_path and os.path.exists(logo_path):
        page.insert_image(
            fitz.Rect(ml, h_top, ml + LOGO_W, h_bot),
            filename=logo_path,
            overlay=True,
        )

    header_text = f"Page {page_number} of {total_pages} - {page_title}"
    page.insert_text(
        fitz.Point(ml + LOGO_W + 6.0, h_base),
        header_text,
        fontname="helv",
        fontsize=HEADER_FOOTER_FONTSIZE,
        color=HEADER_FOOTER_COLOR,
        overlay=True,
    )

    sid_text = f"Submission ID {submission_id}"
    sid_w = _hf_text_width(sid_text)
    page.insert_text(
        fitz.Point(mr_x - sid_w, h_base),
        sid_text,
        fontname="helv",
        fontsize=HEADER_FOOTER_FONTSIZE,
        color=HEADER_FOOTER_COLOR,
        overlay=True,
    )

    if logo_path and os.path.exists(logo_path):
        page.insert_image(
            fitz.Rect(ml, f_top, ml + LOGO_W, f_bot),
            filename=logo_path,
            overlay=True,
        )

    footer_text = f"Page {page_number} of {total_pages}"
    page.insert_text(
        fitz.Point(ml + LOGO_W + 6.0, f_base),
        footer_text,
        fontname="helv",
        fontsize=HEADER_FOOTER_FONTSIZE,
        color=HEADER_FOOTER_COLOR,
        overlay=True,
    )

    sid_footer_text = f"Submission ID: {submission_id}"
    sid_f_w = _hf_text_width(sid_footer_text)
    page.insert_text(
        fitz.Point(mr_x - sid_f_w, f_base),
        sid_footer_text,
        fontname="helv",
        fontsize=HEADER_FOOTER_FONTSIZE,
        color=HEADER_FOOTER_COLOR,
        overlay=True,
    )


def decorate_submission_pages(doc, start_page_number, total_pages, submission_id, logo_path):
    """
    Apply header/footer to every submission page in *doc*.

    Parameters
    ----------
    doc : fitz.Document
        The final merged PDF document.
    start_page_number : int
        1-based page number of the first submission page (usually 3).
    total_pages : int
        Total page count of the final document.
    submission_id : str
        The Turnalyze submission ID.
    logo_path : str
        Filesystem path to the Turnitin-style logo PNG.

    Returns
    -------
    int
        Number of pages decorated.
    """
    start_index = start_page_number - 1
    count = 0
    for i in range(start_index, doc.page_count):
        apply_header_footer(
            doc[i],
            i + 1,
            total_pages,
            "Original Submission",
            submission_id,
            logo_path,
        )
        count += 1
    return count


def apply_canonical_decoration(
    doc,
    total_pages,
    submission_id,
    logo_path,
    page_titles,
):
    """
    Apply ONE canonical header/footer to every page in *doc*.

    Parameters
    ----------
    doc : fitz.Document
        The final merged PDF document.
    total_pages : int
        Total page count of the final document.
    submission_id : str
        The Turnalyze submission ID.
    logo_path : str
        Filesystem path to the Turnitin-style logo PNG.
    page_titles : dict
        Mapping of 0-based page index to section title string.
    """
    logo_aspect = 295.0 / 960.0
    logo_w = 50.0
    logo_h = logo_w * logo_aspect

    left_margin_ratio = 0.065
    header_top_ratio = 0.028
    footer_bottom_ratio = 0.028

    page_font_size = 8.5
    sid_font_size = 7.5
    text_color = (0.2, 0.2, 0.2)
    line_color = (0.85, 0.85, 0.85)
    line_width = 0.5

    font = fitz.Font("helv")

    for i in range(doc.page_count):
        page = doc[i]
        PW = page.rect.width
        PH = page.rect.height

        ml = max(20.0, PW * left_margin_ratio)
        mr_x = PW - ml

        header_top = max(15.0, PH * header_top_ratio)
        footer_bottom = max(15.0, PH * footer_bottom_ratio)

        page.draw_rect(
            fitz.Rect(0.5, 0.5, PW - 0.5, PH - 0.5),
            color=line_color,
            width=line_width,
            overlay=True,
        )

        if logo_path and os.path.exists(logo_path):
            page.insert_image(
                fitz.Rect(ml, header_top, ml + logo_w, header_top + logo_h),
                filename=logo_path,
                overlay=True,
            )

        page_title = page_titles.get(i, "Original Submission")
        header_text = f"Page {i + 1} of {total_pages} - {page_title}"
        page.insert_text(
            fitz.Point(ml + logo_w + 6.0, header_top + logo_h * 0.65),
            header_text,
            fontname="helv",
            fontsize=page_font_size,
            color=text_color,
            overlay=True,
        )

        sid_text = f"Submission ID: {submission_id}"
        sid_w = font.text_length(sid_text, fontsize=sid_font_size)
        page.insert_text(
            fitz.Point(mr_x - sid_w, header_top + logo_h * 0.65),
            sid_text,
            fontname="helv",
            fontsize=sid_font_size,
            color=text_color,
            overlay=True,
        )

        if logo_path and os.path.exists(logo_path):
            page.insert_image(
                fitz.Rect(ml, PH - footer_bottom - logo_h, ml + logo_w, PH - footer_bottom),
                filename=logo_path,
                overlay=True,
            )

        footer_text = f"Page {i + 1} of {total_pages}"
        page.insert_text(
            fitz.Point(ml + logo_w + 6.0, PH - footer_bottom - logo_h * 0.35),
            footer_text,
            fontname="helv",
            fontsize=page_font_size,
            color=text_color,
            overlay=True,
        )

        sid_f_text = f"Submission ID: {submission_id}"
        sid_f_w = font.text_length(sid_f_text, fontsize=sid_font_size)
        page.insert_text(
            fitz.Point(mr_x - sid_f_w, PH - footer_bottom - logo_h * 0.35),
            sid_f_text,
            fontname="helv",
            fontsize=sid_font_size,
            color=text_color,
            overlay=True,
        )

