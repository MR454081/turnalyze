import sys
import tempfile
from pathlib import Path

import fitz

sys.path.append(str(Path(__file__).resolve().parents[1]))

from pdf_converter import highlight_pdf_text
from report_generator import create_report_pdf


def test_report_render_and_highlight():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        source_pdf = tmp_path / "input.pdf"
        highlighted_pdf = tmp_path / "highlighted.pdf"
        output_pdf = tmp_path / "report.pdf"

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "This sentence appears AI generated. This is a second sentence for the report.")
        doc.save(source_pdf)
        doc.close()

        highlight_pdf_text(str(source_pdf), str(highlighted_pdf), text_content="This sentence appears AI generated. This is a second sentence for the report.")
        create_report_pdf(
            str(output_pdf),
            {
                "filename": "sample.pdf",
                "submission_id": "test-001",
                "upload_date": "1 Aug 2026",
                "pages": 1,
                "words": 12,
                "characters": 80,
                "file_size": "0.1 MB",
                "ai_score": 72,
                "human_score": 28,
                "status": "AI",
            },
            source_pdf_path=str(source_pdf),
            highlighted_pdf_path=str(highlighted_pdf),
            text_content="This sentence appears AI generated. This is a second sentence for the report.",
        )

        assert output_pdf.exists()
        assert output_pdf.stat().st_size > 0
        assert highlighted_pdf.exists()
        assert highlighted_pdf.stat().st_size > 0
