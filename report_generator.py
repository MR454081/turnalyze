import os
import re
import fitz

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright

from pdf_converter import apply_canonical_decoration


def create_report_pdf(
    output_pdf_path,
    report_data,
    source_pdf_path=None,
    highlighted_pdf_path=None,
    text_content=None
):
    """
    Generate:

        Page 1 = Cover page
        Page 2 = AI Writing Overview
        Page 3+ = Original/highlighted submission

    The first two pages use the SAME report.html and
    report.css as the browser.

    CSS is embedded directly into the generated HTML so
    Chromium cannot fail to load report.css.
    """

    # =========================================================
    # DIRECTORIES
    # =========================================================

    base_dir = os.path.dirname(
        os.path.abspath(__file__)
    )

    template_dir = os.path.join(
        base_dir,
        "templates"
    )

    static_dir = os.path.join(
        base_dir,
        "static"
    )

    css_path = os.path.join(
        static_dir,
        "css",
        "report.css"
    )

    output_dir = os.path.dirname(
        os.path.abspath(output_pdf_path)
    )

    os.makedirs(
        output_dir,
        exist_ok=True
    )

    # =========================================================
    # READ CSS DIRECTLY
    # =========================================================

    if not os.path.isfile(css_path):
        raise FileNotFoundError(
            f"report.css not found: {css_path}"
        )

    with open(
        css_path,
        "r",
        encoding="utf-8"
    ) as css_file:

        css_content = css_file.read()

    print(
        "Loaded report.css:",
        css_path
    )

    print(
        "CSS characters:",
        len(css_content)
    )

    # =========================================================
    # JINJA
    # =========================================================

    env = Environment(
        loader=FileSystemLoader(
            template_dir
        ),
        autoescape=select_autoescape(
            ["html", "xml"]
        )
    )

    # =========================================================
    # url_for()
    # =========================================================

    def fake_url_for(
        endpoint,
        **values
    ):

        if endpoint == "static":

            filename = values.get(
                "filename",
                ""
            )

            absolute_path = os.path.abspath(
                os.path.join(
                    static_dir,
                    filename
                )
            )

            return (
                "file:///"
                + absolute_path.replace(
                    "\\",
                    "/"
                )
            )

        if endpoint == "download_report":

            report_id = values.get(
                "report_id"
            )

            return f"/download/{report_id}"

        if endpoint == "report_preview":

            report_id = values.get(
                "report_id"
            )

            return f"/report-preview/{report_id}"

        return f"/{endpoint}"

    env.globals["url_for"] = fake_url_for

    # =========================================================
    # LOAD REPORT TEMPLATE
    # =========================================================

    template = env.get_template(
        "report.html"
    )

    submission_pages = int(
        report_data.get(
            "pages"
        ) or 0
    )

    total_pages = (
        submission_pages + 2
    )

    # =========================================================
    # TEMPLATE DATA
    # =========================================================

    ctx = {

        "report_id":
            report_data.get("id"),

        "filename":
            report_data.get(
                "filename",
                "Document"
            ),

        "student_name":
            report_data.get(
                "student_name"
            ) or report_data.get(
                "filename",
                "Document"
            ),

        "document_title":
            report_data.get(
                "document_title"
            ) or report_data.get(
                "filename",
                "Document"
            ),

        "category":
            report_data.get(
                "category",
                "Assignment Submission"
            ),

        "submission_date":
            report_data.get(
                "upload_date",
                ""
            ),

        "upload_date":
            report_data.get(
                "upload_date",
                ""
            ),

        "download_date":
            report_data.get(
                "upload_date",
                ""
            ),

        "submission_id":
            report_data.get(
                "submission_id",
                "N/A"
            ),

        "pages":
            submission_pages,

        "words":
            report_data.get(
                "words"
            ) or 0,

        "characters":
            report_data.get(
                "characters"
            ) or 0,

        "file_size":
            report_data.get(
                "file_size",
                "0 MB"
            ),

        "ai_score":
            report_data.get(
                "ai_score"
            ) or 0,

        "human_score":
            report_data.get(
                "human_score"
            ) or 0,

        "status":
            report_data.get(
                "status",
                "Completed"
            ),

        "html_content":
            report_data.get(
                "html_content",
                ""
            ),

        "ai_only":
            report_data.get(
                "ai_only",
                report_data.get(
                    "ai_score"
                ) or 0
            ),

        "ai_paraphrased":
            report_data.get(
                "ai_paraphrased",
                0
            ),

        "page_count":
            total_pages,

        "pdf_filename":
            os.path.basename(
                report_data.get(
                    "pdf_path"
                ) or ""
            ),

        "pdf_url":
            fake_url_for(
                "report_preview",
                report_id=report_data.get(
                    "id"
                )
            ),

        "university":
            report_data.get(
                "university",
                "Turnalyze University"
            ),

        "for_pdf":
            True,

        "report_path":
            report_data.get(
                "report_path",
                ""
            ),
    }

    # =========================================================
    # RENDER HTML
    # =========================================================

    html_string = template.render(**ctx)

    # =========================================================
    # EMBED CSS DIRECTLY
    #
    # Keep the SAME report.css rules used by the browser, but embed
    # them so Chromium cannot fail to load the stylesheet.
    # =========================================================

    css_tag = (
        '<style id="turnalyze-report-css">\n'
        + css_content
        + '\n</style>'
    )

    html_string = re.sub(
        r'<link[^>]+report\.css[^>]*>',
        css_tag,
        html_string,
        flags=re.IGNORECASE
    )

    # =========================================================
    # TEMP FILES
    # =========================================================

    temp_html = output_pdf_path + ".html"
    temp_front_pdf = output_pdf_path + ".front.pdf"

    with open(
        temp_html,
        "w",
        encoding="utf-8"
    ) as html_file:
        html_file.write(html_string)

    # =========================================================
    # FILE URL
    # =========================================================

    html_url = (
        "file:///"
        + os.path.abspath(temp_html).replace("\\", "/")
    )

        # =========================================================
    # PLAYWRIGHT / CHROMIUM
    # =========================================================

    try:
        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--allow-file-access-from-files",
                    "--disable-web-security",
                ]
            )

            page = browser.new_page(
                viewport={
                    "width": 1280,
                    "height": 1800,
                },
                device_scale_factor=1,
            )

            # =====================================================
            # LOAD HTML
            # =====================================================

            page.emulate_media(media="screen")

            page.goto(
                html_url,
                wait_until="networkidle"
            )

            # =====================================================
            # WAIT FOR IMAGES
            # =====================================================

            page.wait_for_function(
                """
                () => Array.from(document.images)
                    .every(img => img.complete)
                """
            )

            # =====================================================
            # WAIT FOR FONTS
            # =====================================================

            page.evaluate(
                """
                async () => {
                    if (document.fonts) {
                        await document.fonts.ready;
                    }
                }
                """
            )

            page.wait_for_timeout(500)

            # =====================================================
            # DEBUG LAYOUT
            # =====================================================

            css_status = page.evaluate(
                """
                () => {

                    const cover =
                        document.querySelector(".cover-page");

                    const overview =
                        document.querySelector(".overview-page");

                    const summary =
                        document.querySelector(".summary");

                    const notice =
                        document.querySelector(".notice-box");

                    const faq =
                        document.querySelector(".faq");

                    const faqRight =
                        document.querySelector(".faq-right");

                    const stats =
                        document.querySelector(".cover-stats");

                    const detailsWrapper =
                        document.querySelector(
                            ".cover-details-wrapper"
                        );

                    const coverRect =
                        cover?.getBoundingClientRect();

                    const overviewRect =
                        overview?.getBoundingClientRect();

                    const summaryRect =
                        summary?.getBoundingClientRect();

                    const noticeRect =
                        notice?.getBoundingClientRect();

                    const faqRect =
                        faq?.getBoundingClientRect();

                    const faqRightRect =
                        faqRight?.getBoundingClientRect();

                    const statsRect =
                        stats?.getBoundingClientRect();

                    return {

                        viewportWidth:
                            window.innerWidth,

                        viewportHeight:
                            window.innerHeight,

                        responsive900:
                            window.innerWidth <= 900,

                        bodyWidth:
                            document.body
                                .getBoundingClientRect()
                                .width,

                        coverWidth:
                            coverRect?.width,

                        coverHeight:
                            coverRect?.height,

                        overviewWidth:
                            overviewRect?.width,

                        overviewHeight:
                            overviewRect?.height,

                        summaryDisplay:
                            summary
                                ? getComputedStyle(summary).display
                                : null,

                        summaryFlexDirection:
                            summary
                                ? getComputedStyle(summary)
                                    .flexDirection
                                : null,

                        noticeX:
                            noticeRect?.x,

                        noticeY:
                            noticeRect?.y,

                        statsX:
                            statsRect?.x,

                        statsY:
                            statsRect?.y,

                        detailsDisplay:
                            detailsWrapper
                                ? getComputedStyle(
                                    detailsWrapper
                                ).display
                                : null,

                        detailsFlexDirection:
                            detailsWrapper
                                ? getComputedStyle(
                                    detailsWrapper
                                ).flexDirection
                                : null,

                        faqDisplay:
                            faq
                                ? getComputedStyle(faq).display
                                : null,

                        faqFlexDirection:
                            faq
                                ? getComputedStyle(faq)
                                    .flexDirection
                                : null,

                        faqRightX:
                            faqRightRect?.x,

                        faqRightY:
                            faqRightRect?.y
                    };
                }
                """
            )

            print("")
            print("======================================")
            print("TURNALYZE PDF LAYOUT DEBUG")
            print("======================================")

            for key, value in css_status.items():
                print(f"{key}: {value}")

            print("======================================")
            print("")

            # =====================================================
            # REMOVE BROWSER-ONLY ELEMENTS
            # =====================================================

            page.evaluate(
                """
                () => {

                    const downloadBar =
                        document.querySelector(
                            ".report-download-bar"
                        );

                    if (downloadBar) {
                        downloadBar.remove();
                    }

                    const container =
                        document.getElementById(
                            "pdf-container"
                        );

                    if (container) {
                        container.remove();
                    }

                    document
                        .querySelectorAll(".page-break")
                        .forEach(el => el.remove());

                    const decorationSelectors = [
                        ".cover-header",
                        ".cover-footer",
                        ".overview-page .header",
                        ".overview-page .footer"
                    ];

                    decorationSelectors.forEach(selector => {
                        document.querySelectorAll(selector).forEach(el => {
                            el.remove();
                        });
                    });
                }
                """
            )

            page.wait_for_timeout(300)

            # =====================================================
            # CREATE FRONT PDF
            # =====================================================

            page.pdf(
                path=temp_front_pdf,

                format="Letter",

                print_background=True,

                prefer_css_page_size=True,

                margin={
                    "top": "0mm",
                    "right": "0mm",
                    "bottom": "0mm",
                    "left": "0mm",
                },

                display_header_footer=False,
            )

            browser.close()

        # =========================================================
        # OPEN FRONT PDF
        # =========================================================

        if not os.path.isfile(temp_front_pdf):
            raise RuntimeError(
                "Chromium failed to create PDF."
            )

        front_doc = fitz.open(
            temp_front_pdf
        )

        print(
            "Chromium generated:",
            front_doc.page_count,
            "pages"
        )

        if front_doc.page_count < 2:
            front_doc.close()

            raise RuntimeError(
                "Cover + Overview did not generate as two pages."
            )
    
        # =====================================================
        # FINAL PDF
        # =====================================================

        final_doc = fitz.open()

        # ONLY FIRST TWO PAGES FROM CHROMIUM
        final_doc.insert_pdf(
            front_doc,
            from_page=0,
            to_page=1
        )

        front_doc.close()

        # =====================================================
        # APPEND SUBMISSION
        # =====================================================

        submission_path = None

        if (
            highlighted_pdf_path
            and os.path.isfile(highlighted_pdf_path)
        ):
            submission_path = highlighted_pdf_path

        elif (
            source_pdf_path
            and os.path.isfile(source_pdf_path)
        ):
            submission_path = source_pdf_path

        submission_pages_actual = 0

        if submission_path:
            submission_doc = fitz.open(submission_path)

            submission_pages_actual = (
                submission_doc.page_count
            )

            for i in range(submission_doc.page_count):
                src_page = submission_doc[i]
                pw = src_page.rect.width
                ph = src_page.rect.height

                if abs(pw - 595.0) < 5.0 and abs(ph - 842.0) < 5.0:
                    scale = min(612.0 / pw, 792.0 / ph)
                    new_w = pw * scale
                    new_h = ph * scale
                    offset_x = (612.0 - new_w) / 2.0
                    offset_y = (792.0 - new_h) / 2.0

                    new_page = final_doc.new_page(
                        width=612.0,
                        height=792.0
                    )

                    new_page.show_pdf_page(
                        fitz.Rect(
                            offset_x,
                            offset_y,
                            offset_x + new_w,
                            offset_y + new_h
                        ),
                        submission_doc,
                        i,
                        keep_proportion=True,
                    )

                    for annot in src_page.annots():
                        quads = annot.vertices
                        if quads:
                            new_quads = []
                            for q in quads:
                                new_quads.append(
                                    (
                                        q[0] * scale + offset_x,
                                        q[1] * scale + offset_y,
                                    )
                                )
                            xs = [q[0] for q in new_quads]
                            ys = [q[1] for q in new_quads]
                            new_rect = fitz.Rect(
                                min(xs),
                                min(ys),
                                max(xs),
                                max(ys)
                            )
                            new_annot = new_page.add_highlight_annot(
                                new_rect
                            )
                            if new_annot:
                                new_annot.set_colors(
                                    stroke=annot.colors.get(
                                        "stroke",
                                        (1, 1, 0)
                                    )
                                )
                                new_annot.set_opacity(
                                    annot.opacity
                                )
                                new_annot.update()
                else:
                    final_doc.insert_pdf(
                        submission_doc,
                        from_page=i,
                        to_page=i
                    )

            submission_doc.close()

        # =====================================================
        # VALIDATE
        # =====================================================

        expected_pages = (
            2 + submission_pages_actual
        )

        print(
            "Final expected pages:",
            expected_pages
        )

        print(
            "Final actual pages:",
            final_doc.page_count
        )

        if final_doc.page_count != expected_pages:
            final_doc.close()

            raise RuntimeError(
                "Final page count mismatch."
            )

        # =====================================================
        # APPLY CANONICAL HEADER/FOOTER TO ALL PAGES
        # =====================================================

        logo_path = os.path.join(
            static_dir,
            "images",
            "turnitin-logo.png"
        )

        submission_id = report_data.get(
            "submission_id",
            "N/A"
        )

        total_pages = final_doc.page_count

        page_titles = {
            0: "Cover Page",
            1: "AI Writing Overview",
        }
        for i in range(2, total_pages):
            page_titles[i] = (
                "AI Writing Submission"
                if i == 2
                else "Original Submission"
            )

        apply_canonical_decoration(
            final_doc,
            total_pages=total_pages,
            submission_id=submission_id,
            logo_path=logo_path,
            page_titles=page_titles,
        )

        print(
            "Canonical decoration applied to pages:",
            total_pages
        )

        print(
            "Total final pages:",
            final_doc.page_count
        )

        # =====================================================
        # SAVE
        # =====================================================

        final_doc.save(
            output_pdf_path,
            garbage=4,
            deflate=True
        )

        final_doc.close()

    finally:
        for file_path in [
            temp_html,
            temp_front_pdf
        ]:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass

    return output_pdf_path