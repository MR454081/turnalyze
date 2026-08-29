"""
Test whether 'hidden' attribute prevents file submission.
Uses Flask test client to compare POST data.
"""
import os
import io
import requests

BASE_URL = "http://10.2.0.2:5000"

# Login to get session cookie
session = requests.Session()
login_resp = session.post(f"{BASE_URL}/login", data={
    "email": "admin@turnalyze.com",
    "password": "admin123",
})
print(f"Login: {login_resp.status_code}")

# Check session
dashboard = session.get(f"{BASE_URL}/dashboard")
print(f"Dashboard: {dashboard.status_code}")
has_user = "Dashboard" in dashboard.text
print(f"Has dashboard content: {has_user}")

# Now try uploading via requests with a hidden file input
# The upload.html uses hidden attribute. Let's simulate the form submission.
source_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "2032AB202683_1.docx")
print(f"\nSource file: {source_file}")

with open(source_file, "rb") as f:
    file_data = f.read()

# Try uploading with requests (which simulates a normal HTTP POST, not browser behavior)
upload_resp = session.post(
    f"{BASE_URL}/upload",
    files={"file": ("2032AB202683_1.docx", file_data, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    allow_redirects=False,
)
print(f"\nDirect upload (requests): {upload_resp.status_code}")
print(f"  Location: {upload_resp.headers.get('location', 'N/A')}")
if "text" in upload_resp.headers.get("content-type", ""):
    # Check for flash messages
    import re
    flashes = re.findall(r'class=["\'][^"\']*flash[^"\']*["\'][^>]*>(.*?)</div>', upload_resp.text, re.DOTALL)
    flashes += re.findall(r'<p[^>]*>(Please choose|No file|Only PDF)</p>', upload_resp.text, re.IGNORECASE)
    print(f"  Flash messages: {flashes}")
    if not flashes:
        # Try to find any text content
        texts = re.findall(r'<p[^>]*>(.*?)</p>', upload_resp.text, re.DOTALL)
        print(f"  Text content: {[t.strip() for t in texts[:10]]}")

# Now test with Playwright to capture the actual POST data sent
print("\n\n=== Testing with Playwright: capturing exact POST body ===")
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1280, "height": 1800}).new_page()

    # Login
    page.goto(f"{BASE_URL}/")
    page.fill('input[name="email"]', "admin@turnalyze.com")
    page.fill('input[name="password"]', "admin123")
    page.click('form button[type="submit"]')
    page.wait_for_timeout(3000)

    # Navigate to upload
    page.goto(f"{BASE_URL}/upload")
    page.wait_for_timeout(1000)

    # Capture the POST request body as a buffer
    post_bodies = []

    def capture_request(req):
        if req.url.endswith("/upload") and req.method == "POST":
            try:
                body = req.post_data
                post_bodies.append({
                    "has_body": body is not None,
                    "body_len": len(body) if body else 0,
                    "body_preview": body[:300] if body else "",
                })
            except:
                post_bodies.append({"error": "Could not read body"})

    page.on("request", capture_request)

    # Select file
    with page.expect_file_chooser() as fc_info:
        page.click('label[for="fileInput"]')
    fc = fc_info.value
    fc.set_files(source_file)
    page.wait_for_timeout(500)

    # Click Analyze
    page.click('.analyze-btn')
    page.wait_for_timeout(5000)

    print(f"POST body captures: {len(post_bodies)}")
    for pb in post_bodies:
        print(f"  {pb}")

    # Also try using page.request to manually POST with the file
    # This simulates what the browser should send
    print("\n\n=== Manual POST with file (simulating form submission) ===")
    with open(source_file, "rb") as f:
        resp = page.request.post(
            f"{BASE_URL}/upload",
            files={"file": ("2032AB202683_1.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            cookies=page.context.cookies(),
            follow_redirects=False,
        )
    print(f"Manual POST: {resp.status}")
    print(f"  Location: {resp.headers.get('location', 'N/A')}")

    browser.close()
