(() => {
    pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.4.168/pdf.worker.min.js";

    const container = document.getElementById("pdf-container");
    if (!container) {
        return;
    }

    const pdfUrl = window.TURNALYZE_PDF_URL || "";
    const submissionId = window.TURNALYZE_SUBMISSION_ID || "";

    console.log("PDF URL:", pdfUrl);

    if (!pdfUrl) {
        console.error("PDF URL is empty or undefined.");
        container.innerHTML = '<div class="pdf-error">PDF URL not provided.</div>';
        return;
    }

    let scale = 1.15;

    async function renderTextLayer(page, viewport, wrapper) {
        try {
            const textLayer = document.createElement("div");
            textLayer.className = "textLayer";
            textLayer.style.width = `${viewport.width}px`;
            textLayer.style.height = `${viewport.height}px`;
            wrapper.appendChild(textLayer);

            const textContent = await page.getTextContent();
            pdfjsLib.renderTextLayer({
                textContentSource: textContent,
                container: textLayer,
                viewport
            });
        } catch (err) {
            console.error("Error rendering text layer:", err);
        }
    }

    async function renderPage(pdf, originalPageNumber, totalReportPages) {
        console.log("Rendering original page:", originalPageNumber);

        const page = await pdf.getPage(originalPageNumber);
        const viewport = page.getViewport({ scale });
        const reportPageNumber = originalPageNumber + 2;

        const wrapper = document.createElement("div");
        wrapper.className = "original-page page document-page";

        const header = document.createElement("header");
        header.className = "header";
        header.innerHTML = `
            <div class="logo-area">
                <img src="/static/images/turnitin-logo.png" class="logo" alt="Turnalyze">
            </div>
            <div class="page-info">Page ${reportPageNumber} of ${totalReportPages} • Original Submission</div>
            <div class="submission-id">Submission ID ${submissionId}</div>
        `;

        const content = document.createElement("section");
        content.className = "page-content document-content";

        const card = document.createElement("div");
        card.className = "pdf-page-card";

        const shell = document.createElement("div");
        shell.className = "canvas-shell";
        shell.style.width = `${viewport.width}px`;
        shell.style.height = `${viewport.height}px`;

        const canvas = document.createElement("canvas");
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        shell.appendChild(canvas);

        card.appendChild(shell);
        content.appendChild(card);

        const footer = document.createElement("footer");
        footer.className = "footer";
        footer.innerHTML = `
            <img src="/static/images/turnitin-logo.png" class="footer-logo" alt="Turnalyze">
            <span class="footer-page">Page ${reportPageNumber} of ${totalReportPages}</span>
            <span class="footer-id">Submission ID: ${submissionId}</span>
        `;

        wrapper.appendChild(header);
        wrapper.appendChild(content);
        wrapper.appendChild(footer);

        container.appendChild(wrapper);

        const ctx = canvas.getContext("2d");
        await page.render({ canvasContext: ctx, viewport }).promise;
        await renderTextLayer(page, viewport, shell);
    }

    async function loadPDF() {
        container.innerHTML = '<div class="pdf-loading">Loading original submission…</div>';

        try {
            const pdf = await pdfjsLib.getDocument(pdfUrl).promise;
            console.log("Original PDF pages:", pdf.numPages);

            container.innerHTML = "";
            const totalReportPages = pdf.numPages + 2;

            for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber++) {
                await renderPage(pdf, pageNumber, totalReportPages);
            }
        } catch (err) {
            console.error("Failed to load PDF:", err);
            container.innerHTML = `<div class="pdf-error">Unable to load the original submission. ${err.message || err}</div>`;
        }
    }

    loadPDF().catch((err) => {
        console.error("PDF initialization error:", err);
    });
})();