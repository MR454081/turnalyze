"""
Debug the POST /upload response to understand why the server redirects back.
Check: flash messages, response status, whether file is in POST data.
"""
import os
import re
from playwright.sync_api import sync_playwright

BASE_URL = "http://10.2.0.2:5000"
SOURCE_DOCX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "2032AB202683_1.docx")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1280, "height": 1800}).new_page()

    # Track response of POST /upload
    post_response_info = []
    page.on("response", lambda resp: post_response_info.append({
        "url": resp.url,
        "status": resp.status,
        "headers": dict(resp.headers),
    }) if "upload" in resp.url and resp.request.method == "POST" else None)

    # Login
    page.goto(f"{BASE_URL}/")
    page.fill('input[name="email"]', "admin@turnalyze.com")
    page.fill('input[name="password"]', "admin123")
    page.click('form button[type="submit"]')
    page.wait_for_timeout(3000)

    # Navigate to upload
    page.goto(f"{BASE_URL}/upload")
    page.wait_for_timeout(2000)

    # Verify session is set
    cookies = page.context.cookies()
    session_cookie = [c for c in cookies if "session" in c["name"].lower()]
    print(f"Session cookies: {len(session_cookie)}")
    if session_cookie:
        print(f"  Session cookie present: {session_cookie[0]['name']}")

    # Select file via label click
    with page.expect_file_chooser() as fc_info:
        page.click('label[for="fileInput"]')
    fc = fc_info.value
    fc.set_files(SOURCE_DOCX)
    page.wait_for_timeout(500)

    file_count = page.evaluate('() => document.getElementById("fileInput").files.length')
    print(f"Files selected: {file_count}")

    # Check if the file input has a value
    file_value = page.evaluate('() => document.getElementById("fileInput").value')
    print(f"File input value: '{file_value[:100]}'")

    # Click Analyze
    post_response_info.clear()
    page.click('.analyze-btn')
    page.wait_for_timeout(5000)

    print(f"\nPOST /upload responses: {len(post_response_info)}")
    for resp in post_response_info:
        print(f"  Status: {resp['status']}")
        print(f"  URL: {resp['url']}")
        location = resp.get("headers", {}).get("location", "")
        print(f"  Location redirect: {location}")

    print(f"\nFinal URL: {page.url}")

    # Get page content after submission
    page_html = page.content()

    # Look for flash messages
    flash_messages = re.findall(r'class=["\'][^"\']*alert[^"\']*["\'][^>]*>(.*?)</', page_html, re.DOTALL)
    flash_messages += re.findall(r'class=["\'][^"\']*flash[^"\']*["\'][^>]*>(.*?)</', page_html, re.DOTALL)
    flash_messages += re.findall(r'<p[^>]*class=["\'][^"\']*message[^"\']*["\'][^>]*>(.*?)</p>', page_html, re.DOTALL)

    # Also look for any text that looks like a flash message
    alert_patterns = [
        "Please choose a file",
        "No file selected",
        "Only PDF and DOCX",
        "Please login first",
        "Unable to read",
        "Login successful",
        "Invalid",
    ]
    print("\nChecking for flash/error messages in page:")
    for pattern in alert_patterns:
        if pattern.lower() in page_html.lower():
            # Find the context around the match
            idx = page_html.lower().find(pattern.lower())
            start = max(0, idx - 50)
            end = min(len(page_html), idx + len(pattern) + 100)
            context = page_html[start:end].replace('\n', ' ').strip()
            print(f"  FOUND '{pattern}': ...{context}...")

    # Check if file input still has the file
    file_count_after = page.evaluate('() => document.getElementById("fileInput").files.length')
    print(f"\nFile input files after submission: {file_count_after}")

    # Check if the form was re-rendered (page reload)
    print(f"\nCurrent URL: {page.url}")
    if page.url.endswith("/upload"):
        print("Server redirected back to /upload")
    elif "report" in page.url:
        print("Server redirected to report page!")
    else:
        print(f"Server redirected to: {page.url}")

    browser.close()
    print("\n=== Done ===")
