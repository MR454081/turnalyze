"""
Debug: Check what's actually happening server-side.
1. Follow redirects to see flash messages
2. Check cookies/session
3. Test with direct file upload (bypassing the form)
"""
import os
import requests

BASE_URL = "http://10.2.0.2:5000"
SOURCE_DOCX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "2032AB202683_1.docx")

session = requests.Session()

# Login
login_resp = session.post(f"{BASE_URL}/login", data={
    "email": "admin@turnalyze.com",
    "password": "admin123",
}, allow_redirects=True)
print(f"Login: {login_resp.status_code}, final URL: {login_resp.url}")

# Check session cookie
cookies = session.cookies.get_dict()
print(f"Session cookies: {list(cookies.keys())}")

# Check upload page
upload_get = session.get(f"{BASE_URL}/upload")
print(f"\nUpload page GET: {upload_get.status_code}")
print(f"Contains 'analyze-btn': {'analyze-btn' in upload_get.text}")

# Now upload the file directly using requests (bypassing browser)
print(f"\n--- Direct file upload via requests ---")
print(f"File: {SOURCE_DOCX}, size: {os.path.getsize(SOURCE_DOCX)}")

with open(SOURCE_DOCX, "rb") as f:
    upload_resp = session.post(
        f"{BASE_URL}/upload",
        files={"file": ("2032AB202683_1.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        allow_redirects=False,
    )

print(f"POST /upload: {upload_resp.status_code}")
print(f"  Location: {upload_resp.headers.get('location', 'N/A')}")
print(f"  Content-Type: {upload_resp.headers.get('content-type', 'N/A')}")

# Follow redirect to see flash message
if upload_resp.status_code == 302:
    redirect_url = upload_resp.headers.get("location")
    if redirect_url.startswith("/"):
        redirect_url = BASE_URL + redirect_url
    print(f"\n  Following redirect to: {redirect_url}")
    final_resp = session.get(redirect_url)
    print(f"  Redirected page: {final_resp.status_code}")

    # Check for flash messages
    import re
    # Flash messages in Flask are stored in a special div
    flash_msgs = re.findall(r'class="alert[^"]*"[^>]*>(.*?)</div>', final_resp.text, re.DOTALL)
    if not flash_msgs:
        flash_msgs = re.findall(r'<p[^>]*class=["\']flashes["\']?[^>]*>(.*?)</p>', final_resp.text, re.DOTALL)
    if not flash_msgs:
        # Try to find the flash message text in the page
        for msg in ["Please choose a file", "No file selected", "Only PDF", "Please login", "Unable to read", "Invalid"]:
            if msg in final_resp.text:
                print(f"\n  FLASH MESSAGE FOUND: '{msg}'")
                # Get context
                idx = final_resp.text.find(msg)
                start = max(0, idx - 200)
                end = min(len(final_resp.text), idx + 200)
                context = final_resp.text[start:end].replace('\n', ' ').strip()
                print(f"  Context: ...{context}...")
                break
    else:
        for fm in flash_msgs:
            print(f"  Flash: {fm.strip()[:200]}")

# Also check: what if the file has a different extension?
print("\n\n--- Testing with a .txt file (should be rejected) ---")
with open(SOURCE_DOCX, "rb") as f:
    txt_resp = session.post(
        f"{BASE_URL}/upload",
        files={"file": ("test.txt", f, "text/plain")},
        allow_redirects=True,
    )
print(f"TXT upload: {txt_resp.status_code}, URL: {txt_resp.url}")
if "Only PDF and DOCX" in txt_resp.text:
    print("  Flash: 'Only PDF and DOCX files are supported.'")

# Test with .docx extension
print("\n--- Testing with correct .docx file ---")
with open(SOURCE_DOCX, "rb") as f:
    docx_resp = session.post(
        f"{BASE_URL}/upload",
        files={"file": ("test.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        allow_redirects=True,
    )
print(f"DOCX upload: {docx_resp.status_code}, URL: {docx_resp.url}")
if "report" in docx_resp.url:
    print("  SUCCESS: Redirected to report page!")
elif docx_resp.url.endswith("/upload"):
    print("  FAILED: Redirected back to upload page")
    # Check for flash messages
    for msg in ["Please choose a file", "No file selected", "Only PDF", "Please login", "Unable to read", "Invalid"]:
        if msg in docx_resp.text:
            print(f"  Flash: '{msg}'")
            break
    else:
        print("  No known flash message found")
        # Print a snippet of the page
        print(f"  Page contains 'alert': {'alert' in docx_resp.text}")
        print(f"  Page contains 'flash': {'flash' in docx_resp.text}")
        print(f"  Page snippet: {docx_resp.text[:1000]}")
