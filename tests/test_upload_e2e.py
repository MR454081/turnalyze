"""
End-to-end Playwright test for the Turnalyze upload and navigation workflow.

Tests:
1. Dashboard -> "Analyze AI Content" with no file -> /reports
2. Dashboard -> select DOCX -> click "Analyze AI Content" -> /report/<id>
3. Verify database score == browser score
"""
import os
import sys
import time
import json
import sqlite3

from playwright.sync_api import sync_playwright, expect

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_URL = "http://127.0.0.1:5000"

# Use the exact file the user selected manually if available,
# otherwise fall back to a known test fixture.
UPLOAD_FILES = [
    os.path.join(BASE_DIR, "uploads", "9483AB21-Aakarshan_TO-MBAS900_1.docx"),
    os.path.join(BASE_DIR, "static", "pdfs", "dbf1c5cac12541f99f94c2508d610f95_test_upload.docx"),
    os.path.join(BASE_DIR, "uploads", "test_upload.docx"),
]

SOURCE_DOCX = None
for path in UPLOAD_FILES:
    if os.path.exists(path):
        SOURCE_DOCX = path
        break

if not SOURCE_DOCX:
    print("ERROR: No test DOCX file found.")
    sys.exit(1)

print(f"Using test DOCX: {SOURCE_DOCX}")


def get_db_ai_score(report_id):
    conn = sqlite3.connect(os.path.join(BASE_DIR, "turnalyze.db"))
    cursor = conn.cursor()
    cursor.execute("SELECT ai_score FROM reports WHERE id=?", (report_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def run_test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 1800})
        page = context.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}"))

        network_requests = []
        page.on("request", lambda req: network_requests.append({
            "url": req.url,
            "method": req.method,
            "resourceType": req.resource_type,
        }))

        # =========================================================
        # STEP 1: Login
        # =========================================================
        print("\n=== STEP 1: Login ===")
        page.goto(f"{BASE_URL}/")
        page.wait_for_timeout(1000)
        page.fill('input[name="email"]', "admin@turnalyze.com")
        page.fill('input[name="password"]', "admin123")
        page.click('form button[type="submit"]')
        page.wait_for_timeout(2000)
        print(f"URL after login: {page.url}")

        # =========================================================
        # STEP 2: Dashboard -> Analyze AI Content (no file)
        # =========================================================
        print("\n=== STEP 2: Click Analyze AI Content with no file ===")
        page.goto(f"{BASE_URL}/dashboard")
        page.wait_for_timeout(1000)
        page.click("#analyzeBtn")
        page.wait_for_timeout(1000)
        print(f"URL after click (no file): {page.url}")
        assert "/reports" in page.url, f"Expected /reports, got {page.url}"
        print("PASS: Navigated to /reports when no file selected")

        # =========================================================
        # STEP 3: Dashboard -> Upload DOCX -> Analyze
        # =========================================================
        print("\n=== STEP 3: Upload DOCX and analyze ===")
        page.goto(f"{BASE_URL}/dashboard")
        page.wait_for_timeout(1000)

        # Attach the real DOCX
        page.locator("#fileInput").set_input_files(SOURCE_DOCX)
        page.wait_for_timeout(500)

        # Verify file is attached
        file_count = page.evaluate("""() => {
            const input = document.getElementById('fileInput');
            return input ? input.files.length : 0;
        }""")
        print(f"File input files length: {file_count}")
        assert file_count == 1, "File was not attached to input"

        displayed_name = page.evaluate("""() => {
            const el = document.querySelector('.file-name');
            return el ? el.textContent : '';
        }""")
        print(f"Displayed filename: {displayed_name}")

        # Click Analyze AI Content
        page.click("#analyzeBtn")
        page.wait_for_timeout(5000)

        print(f"URL after upload click: {page.url}")
        print(f"Console errors: {console_errors}")
        
        # Print relevant network requests
        upload_requests = [r for r in network_requests if "/upload" in r["url"]]
        print(f"Upload-related requests: {len(upload_requests)}")
        for req in upload_requests:
            print(f"  {req['method']} {req['url']}")
        
        # Check if we got redirected back to /upload
        if "/upload" in page.url:
            print("ERROR: Redirected back to /upload - checking why...")
            # Check for flash messages
            flash_messages = page.evaluate("""() => {
                const flashes = document.querySelectorAll('.alert');
                return Array.from(flashes).map(f => f.textContent);
            }""")
            print(f"Flash messages: {flash_messages}")
            
            # Check page content for error clues
            content = page.content()
            if "Please choose a file" in content:
                print("ERROR: 'Please choose a file' flash message found")
            if "No file selected" in content:
                print("ERROR: 'No file selected' flash message found")
            if "Only PDF and DOCX files are supported" in content:
                print("ERROR: File type not supported")
            if "Unable to read document" in content:
                print("ERROR: Document reading failed")

        # Should be on /report/<id>
        assert "/report/" in page.url, f"Expected /report/<id>, got {page.url}"
        report_id = page.url.split("/report/")[-1].split("?")[0]
        print(f"Report ID: {report_id}")

        # =========================================================
        # STEP 4: Verify report page content
        # =========================================================
        print("\n=== STEP 4: Verify report page ===")
        content = page.content()
        assert "AI Writing Overview" in content, "Report page missing 'AI Writing Overview'"
        assert "detected as AI" in content, "Report page missing AI percentage"
        assert report_id in content, f"Report ID {report_id} not found in page"

        db_score = get_db_ai_score(int(report_id))
        print(f"Database AI score: {db_score}")

        # Extract browser AI score from page
        browser_score = page.evaluate("""() => {
            const el = document.querySelector('.summary-left h1');
            if (!el) return null;
            const text = el.textContent || '';
            const match = text.match(/(\\d+)%/);
            return match ? parseInt(match[1]) : null;
        }""")
        print(f"Browser AI score: {browser_score}")

        if db_score is not None and browser_score is not None:
            assert db_score == browser_score, f"Score mismatch: DB={db_score}, Browser={browser_score}"
            print(f"PASS: Database and browser scores match ({db_score}%)")
        else:
            print(f"WARNING: Could not verify score consistency (db={db_score}, browser={browser_score})")

        # =========================================================
        # STEP 5: Navigate back to dashboard and verify reports link
        # =========================================================
        print("\n=== STEP 5: Verify reports navigation ===")
        page.goto(f"{BASE_URL}/dashboard")
        page.wait_for_timeout(1000)
        page.click("#analyzeBtn")
        page.wait_for_timeout(1000)
        assert "/reports" in page.url, f"Expected /reports, got {page.url}"
        print("PASS: Dashboard -> Analyzed AI Content -> /reports")

        browser.close()
        print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_test()
