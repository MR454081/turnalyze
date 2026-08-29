"""
Test 1: Hidden file input - does the file get included in POST?
Test 2: Visible file input - does the file get included in POST?
Compare the POST payloads to identify if 'hidden' is causing the file to not be sent.
"""
import os
import re
from playwright.sync_api import sync_playwright

BASE_URL = "http://10.2.0.2:5000"
SOURCE_DOCX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "2032AB202683_1.docx")

print(f"Testing with file: {SOURCE_DOCX} (exists={os.path.exists(SOURCE_DOCX)})")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    # === TEST A: Hidden file input (current state) ===
    print("\n=== TEST A: Hidden file input (current upload.html) ===")
    page = browser.new_context(viewport={"width": 1280, "height": 1800}).new_page()

    # Capture POST request body
    post_data = []
    page.on("request", lambda req: post_data.append({
        "url": req.url,
        "method": req.method,
        "post_data": req.post_data if req.post_data else "",
        "post_data_buffer": req.post_data_buffer if hasattr(req, 'post_data_buffer') else None,
        "headers": dict(req.headers),
    }) if req.method == "POST" else None)

    # Login
    page.goto(f"{BASE_URL}/")
    page.fill('input[name="email"]', "admin@turnalyze.com")
    page.fill('input[name="password"]', "admin123")
    page.click('form button[type="submit"]')
    page.wait_for_timeout(3000)

    # Navigate to upload
    page.goto(f"{BASE_URL}/upload")
    page.wait_for_timeout(1000)

    # Verify the file input is hidden
    input_info = page.evaluate(
        """
        () => {
            const el = document.getElementById('fileInput');
            return {
                hidden: el.hasAttribute('hidden'),
                display: getComputedStyle(el).display,
                type: el.type,
            };
        }
    """
    )
    print(f"File input info: {input_info}")

    # Select file via label click
    with page.expect_file_chooser() as fc_info:
        page.click('label[for="fileInput"]')
    fc = fc_info.value
    fc.set_files(SOURCE_DOCX)
    page.wait_for_timeout(500)

    # Verify file was selected
    file_count = page.evaluate('() => document.getElementById("fileInput").files.length')
    print(f"Files selected: {file_count}")

    # Clear previous POST data
    post_data.clear()

    # Click Analyze
    page.click('.analyze-btn')
    page.wait_for_timeout(5000)

    print(f"POST requests: {len([p for p in post_data if p])}")
    for pd in [p for p in post_data if p]:
        url = pd.get("url", "N/A")
        method = pd.get("method", "N/A")
        post_data_str = pd.get("post_data", "") or ""
        has_boundary = "boundary=" in post_data_str if post_data_str else False
        has_file = "document" in post_data_str.lower() if post_data_str else False
        content_type = pd.get("headers", {}).get("content-type", "")
        print(f"  {method} {url}")
        print(f"  Content-Type: {content_type}")
        print(f"  Has boundary: {has_boundary}")
        print(f"  Has 'document' in body: {has_file}")
        if post_data_str:
            # Check if file name is in the POST data
            has_filename = "docx" in post_data_str.lower() or "2032ab" in post_data_str.lower()
            print(f"  Has filename in body: {has_filename}")
            # Show first 500 chars of POST data
            preview = post_data_str[:500] if isinstance(post_data_str, str) else "binary data"
            print(f"  POST data preview: {preview}")
        else:
            print(f"  POST data: EMPTY or binary")

    print(f"Final URL: {page.url}")

    # Check for flash messages
    flash = page.evaluate(
        """
        () => {
            const alerts = document.querySelectorAll('.alert, .message, [class*="flash"]');
            return Array.from(alerts).map(a => a.textContent.trim());
        }
    """
    )
    print(f"Flash/alert messages: {flash}")

    browser.close()

    # === TEST B: Make file input visible (modify via JS) ===
    print("\n\n=== TEST B: Visible file input (via page.evaluate) ===")
    page = browser.new_context(viewport={"width": 1280, "height": 1800}).new_page()

    # Capture POST request body
    post_data2 = []
    page.on("request", lambda req: post_data2.append({
        "url": req.url,
        "method": req.method,
        "post_data": req.post_data if req.post_data else "",
    }) if req.method == "POST" else None)

    # Login
    page.goto(f"{BASE_URL}/")
    page.fill('input[name="email"]', "admin@turnalyze.com")
    page.fill('input[name="password"]', "admin123")
    page.click('form button[type="submit"]')
    page.wait_for_timeout(3000)

    # Navigate to upload
    page.goto(f"{BASE_URL}/upload")
    page.wait_for_timeout(1000)

    # Make the file input visible via JavaScript
    page.evaluate(
        """
        () => {
            const input = document.getElementById('fileInput');
            // Replace hidden attribute with opacity:0 positioning trick
            input.removeAttribute('hidden');
            input.style.position = 'absolute';
            input.style.opacity = '0';
            input.style.width = '1px';
            input.style.height = '1px';
        }
    """
    )

    input_info2 = page.evaluate(
        """
        () => {
            const el = document.getElementById('fileInput');
            return {
                hidden: el.hasAttribute('hidden'),
                display: getComputedStyle(el).display,
            };
        }
    """
    )
    print(f"File input info (after JS): {input_info2}")

    # Select file via label click
    with page.expect_file_chooser() as fc_info2:
        page.click('label[for="fileInput"]')
    fc2 = fc_info2.value
    fc2.set_files(SOURCE_DOCX)
    page.wait_for_timeout(500)

    file_count2 = page.evaluate('() => document.getElementById("fileInput").files.length')
    print(f"Files selected: {file_count2}")

    # Clear previous POST data
    post_data2.clear()

    # Click Analyze
    page.click('.analyze-btn')
    page.wait_for_timeout(5000)

    print(f"POST requests: {len([p for p in post_data2 if p])}")
    for pd in [p for p in post_data2 if p]:
        url = pd.get("url", "N/A")
        method = pd.get("method", "N/A")
        post_data_str = pd.get("post_data", "") or ""
        has_filename = "docx" in post_data_str.lower() or "2032ab" in post_data_str.lower()
        print(f"  {method} {url}")
        print(f"  Has filename in body: {has_filename}")
        if post_data_str:
            preview = post_data_str[:500] if isinstance(post_data_str, str) else "binary data"
            print(f"  POST data preview: {preview}")
        else:
            print(f"  POST data: EMPTY or binary")

    print(f"Final URL: {page.url}")

    browser.close()
    print("\n=== Done ===")
