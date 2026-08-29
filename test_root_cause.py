"""
Root cause analysis: capture POST data as bytes and follow redirects to see flash messages.
"""
import os
from playwright.sync_api import sync_playwright

BASE_URL = "http://10.2.0.2:5000"
SOURCE_DOCX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "2032AB202683_1.docx")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1280, "height": 1800}).new_page()

    # Capture POST request details including binary data
    post_details = []
    page.on("request", lambda req: post_details.append({
        "method": req.method,
        "url": req.url,
        "has_post_data": req.post_data is not None,
        "post_data_len": len(req.post_data) if req.post_data else 0,
        "has_post_data_buffer": req.post_data_buffer is not None,
        "post_data_buffer_len": len(req.post_data_buffer) if req.post_data_buffer else 0,
    }) if req.method == "POST" and "upload" in req.url else None)

    # Capture responses
    responses = []
    page.on("response", lambda resp: responses.append({
        "url": resp.url,
        "status": resp.status,
        "location": resp.headers.get("location", ""),
    }) if "upload" in resp.url else None)

    # Login
    page.goto(f"{BASE_URL}/")
    page.fill('input[name="email"]', "admin@turnalyze.com")
    page.fill('input[name="password"]', "admin123")
    page.click('form button[type="submit"]')
    page.wait_for_timeout(3000)

    # Navigate to upload
    page.goto(f"{BASE_URL}/upload")
    page.wait_for_timeout(1000)

    # Verify file input hidden state
    input_info = page.evaluate(
        """
        () => {
            const el = document.getElementById('fileInput');
            return {
                has_hidden_attr: el.hasAttribute('hidden'),
                display: getComputedStyle(el).display,
                opacity: getComputedStyle(el).opacity,
                visibility: getComputedStyle(el).visibility,
            };
        }
    """
    )
    print(f"File input styles: {input_info}")

    # Select file
    with page.expect_file_chooser() as fc_info:
        page.click('label[for="fileInput"]')
    fc = fc_info.value
    fc.set_files(SOURCE_DOCX)
    page.wait_for_timeout(500)

    file_count = page.evaluate('() => document.getElementById("fileInput").files.length')
    file_value = page.evaluate('() => document.getElementById("fileInput").value')
    print(f"Files selected: {file_count}, value: {file_value[:80]}")

    # Click Analyze
    post_details.clear()
    responses.clear()
    page.click('.analyze-btn')
    page.wait_for_timeout(5000)

    print(f"\nPOST details:")
    for pd in post_details:
        print(f"  {pd}")

    print(f"\nResponses to /upload:")
    for resp in responses:
        print(f"  URL: {resp['url']}, Status: {resp['status']}, Location: {resp['location']}")

    print(f"\nFinal URL: {page.url}")

    # Follow redirect and check for flash messages
    if page.url.endswith("/upload"):
        # Check page content for flash/error messages
        page_html = page.content()

        # Search for common flash message patterns
        import re
        alerts = re.findall(r'class=["\'][^"\']*(?:alert|flash|error|message)[^"\']*["\'][^>]*>(.*?)</', page_html, re.DOTALL | re.IGNORECASE)
        if alerts:
            print(f"\nFlash/alert messages found:")
            for a in alerts:
                print(f"  {a.strip()[:200]}")

        # Also search for text content that might be a flash message
        flash_patterns = [
            "Please choose a file",
            "No file selected",
            "Only PDF and DOCX",
            "Please login first",
            "Unable to read",
            "Login successful",
            "Invalid",
        ]
        for pattern in flash_patterns:
            if pattern.lower() in page_html.lower():
                # Get surrounding context
                idx = page_html.lower().find(pattern.lower())
                start = max(0, idx - 100)
                end = min(len(page_html), idx + len(pattern) + 200)
                context = page_html[start:end].replace('\n', ' ').strip()
                print(f"\n  FOUND '{pattern}': ...{context}...")

    # Now try: use JavaScript to submit the form with FormData to see what's actually being sent
    print("\n\n=== Using JavaScript FormData to inspect what the browser sends ===")

    # Navigate back to upload and set file again
    page.goto(f"{BASE_URL}/upload")
    page.wait_for_timeout(1000)

    with page.expect_file_chooser() as fc_info:
        page.click('label[for="fileInput"]')
    fc = fc_info.value
    fc.set_files(SOURCE_DOCX)
    page.wait_for_timeout(500)

    # Use JavaScript to create FormData and log what would be sent
    form_data_info = page.evaluate(
        """
        () => {
            const form = document.querySelector('form');
            const formData = new FormData(form);
            const entries = [];
            for (const [key, value] of formData.entries()) {
                if (value instanceof File) {
                    entries.push({key, type: 'File', name: value.name, size: value.size});
                } else {
                    entries.push({key, type: typeof value, value: String(value).substring(0, 100)});
                }
            }
            return {
                entries: entries,
                entryCount: entries.length,
            };
        }
    """
    )
    print(f"FormData entries: {form_data_info}")

    browser.close()
    print("\n=== Done ===")
