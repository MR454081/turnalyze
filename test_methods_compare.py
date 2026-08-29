"""
Verify root cause: hidden attribute prevents file submission.
Test 3 approaches:
A) hidden attribute (current)
B) opacity: 0 (standard invisible-but-submissible approach)
C) display: none via CSS (same as hidden)
"""
import os
from playwright.sync_api import sync_playwright

BASE_URL = "http://10.2.0.2:5000"
SOURCE_DOCX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "2032AB202683_1.docx")

def test_upload_method(label, input_style_attr, remove_hidden):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1280, "height": 1800}).new_page()

        post_bodies = []
        page.on("request", lambda req: post_bodies.append({
            "method": req.method,
            "url": req.url,
            "has_body_str": req.post_data is not None and len(req.post_data) > 0,
            "body_len": len(req.post_data) if req.post_data else 0,
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

        # Modify the file input
        page.evaluate(f"""
            () => {{
                const input = document.getElementById('fileInput');
                if (input) {{
                    if ({str(remove_hidden).lower()}) input.removeAttribute('hidden');
                    if ({repr(input_style_attr)}) input.setAttribute('style', {repr(input_style_attr)});
                    const d = getComputedStyle(input).display;
                    console.log('File input display:', d);
                }}
            }}
        """)

        # Select file
        with page.expect_file_chooser() as fc_info:
            page.click('label[for="fileInput"]')
        fc = fc_info.value
        fc.set_files(SOURCE_DOCX)
        page.wait_for_timeout(500)

        # Click Analyze
        page.click('.analyze-btn')
        page.wait_for_timeout(5000)

        print(f"\n{label}:")
        print(f"  POST requests: {len([p for p in post_bodies if p])}")
        for pb in [p for p in post_bodies if p]:
            print(f"  Method: {pb['method']}, URL: {pb['url']}")
            print(f"  Has body: {pb['has_body_str']}, Body length: {pb['body_len']}")
        print(f"  Final URL: {page.url}")
        if page.url == f"{BASE_URL}/upload":
            print(f"  RESULT: FAILED (redirected back to /upload)")
        else:
            print(f"  RESULT: SUCCESS (redirected to: {page.url})")

        browser.close()

# Test A: Current state (hidden attribute)
test_upload_method("A) hidden attribute (current)", "", False)

# Test B: opacity: 0 (standard invisible approach)
test_upload_method("B) opacity:0, absolute position", "opacity:0;position:absolute;width:1px;height:1px;cursor:pointer;", True)

# Test C: display: none via CSS (same as hidden)
test_upload_method("C) display:none via CSS", "display:none;", False)

print("\n=== Done ===")
