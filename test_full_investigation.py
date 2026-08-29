"""
Comprehensive investigation of the /upload page on the running Flask server.
Tests the exact sequence: Choose File -> select DOCX -> click Analyze -> detect file chooser.
"""
import os
import re
from playwright.sync_api import sync_playwright, expect

BASE_URL = "http://10.2.0.2:5000"
SOURCE_DOCX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample.docx")
SOURCE_PDF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample.pdf")

# If no sample files exist, create a simple test file
if not os.path.exists(SOURCE_DOCX):
    # Try to find any docx in uploads
    upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    if os.path.exists(upload_dir):
        for f in os.listdir(upload_dir):
            if f.endswith(".docx"):
                SOURCE_DOCX = os.path.join(upload_dir, f)
                break

if not os.path.exists(SOURCE_PDF):
    upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    if os.path.exists(upload_dir):
        for f in os.listdir(upload_dir):
            if f.endswith(".pdf"):
                SOURCE_PDF = os.path.join(upload_dir, f)
                break

print(f"Source DOCX: {SOURCE_DOCX} (exists={os.path.exists(SOURCE_DOCX)})")
print(f"Source PDF: {SOURCE_PDF} (exists={os.path.exists(SOURCE_PDF)})")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1280, "height": 1800}).new_page()

    # Capture console messages
    console_messages = []
    page.on("console", lambda msg: console_messages.append(f"[{msg.type}] {msg.text}"))
    page.on("pageerror", lambda exc: console_messages.append(f"[ERROR] {exc}"))

    # Track all network requests
    network_requests = []
    page.on("request", lambda req: network_requests.append({
        "url": req.url,
        "method": req.method,
        "resourceType": req.resource_type,
    }))

    # Track file chooser events
    file_chooser_events = []

    def on_file_chooser(fc):
        file_chooser_events.append("FILE CHOOSER OPENED")

    page.on("file_chooser", on_file_chooser)

    # Track navigations
    nav_events = []
    page.on("load", lambda: nav_events.append("page load"))
    page.on("domcontentloaded", lambda: nav_events.append("DOM content loaded"))

    # Step 1: Login
    print("\n=== Step 1: Login ===")
    page.goto(f"{BASE_URL}/")
    page.wait_for_timeout(1000)
    page.fill('input[name="email"]', "admin@turnalyze.com")
    page.fill('input[name="password"]', "admin123")
    page.click('form button[type="submit"]')
    page.wait_for_timeout(3000)
    print(f"Current URL after login: {page.url}")

    # Step 2: Navigate to upload
    print("\n=== Step 2: Navigate to /upload ===")
    page.goto(f"{BASE_URL}/upload")
    page.wait_for_timeout(2000)

    # Step 3: Get the FULL HTML source
    html = page.content()
    print(f"\nHTML length: {len(html)} chars")

    # Save the full HTML for analysis
    with open("upload_page_rendered.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Saved rendered HTML to upload_page_rendered.html")

    # Step 4: Analyze the HTML
    print("\n=== HTML Analysis ===")

    # 1. All <script> tags
    scripts = re.findall(r'<script[^>]*>(.*?)</script>|<script[^>]*src=["\']([^"\']+)["\']', html, re.DOTALL | re.IGNORECASE)
    print(f"\n1. Script tags: {len(scripts)}")
    for i, s in enumerate(scripts):
        inline = s[0] if s[0] else ""
        src = s[1] if s[1] else ""
        if src:
            print(f"  Script {i}: src={src}")
        elif inline:
            print(f"  Script {i}: inline (len={len(inline)}): {inline[:300]}")

    # 2. All inline event handlers
    onclick_matches = re.findall(r'onclick=["\']([^"\']*)["\']', html)
    onchange_matches = re.findall(r'onchange=["\']([^"\']*)["\']', html)
    onsubmit_matches = re.findall(r'onsubmit=["\']([^"\']*)["\']', html)
    onmouse_matches = re.findall(r'onmouse\w+=["\']([^"\']*)["\']', html)
    print(f"\n2. Inline event handlers:")
    print(f"  onclick: {len(onclick_matches)} -> {onclick_matches}")
    print(f"  onchange: {len(onchange_matches)} -> {onchange_matches}")
    print(f"  onsubmit: {len(onsubmit_matches)} -> {onsubmit_matches}")
    print(f"  onmouse*: {len(onmouse_matches)} -> {onmouse_matches}")

    # 3. #fileInput element
    fileinput_match = re.search(r'<input[^>]*id=["\']fileInput["\'][^>]*>', html, re.DOTALL | re.IGNORECASE)
    if fileinput_match:
        print(f"\n3. #fileInput element: {fileinput_match.group()[:300]}")

    # 4. .upload-btn element
    uploadbtn_match = re.search(r'<label[^>]*class=["\'][^"\']*upload-btn[^"\']*["\'][^>]*>.*?</label>', html, re.DOTALL | re.IGNORECASE)
    if uploadbtn_match:
        print(f"\n4. .upload-btn label: {uploadbtn_match.group()[:300]}")

    # 5. .analyze-btn element
    analyzebtn_match = re.search(r'<button[^>]*class=["\'][^"\']*analyze-btn[^"\']*["\'][^>]*>.*?</button>', html, re.DOTALL | re.IGNORECASE)
    if analyzebtn_match:
        print(f"\n5. .analyze-btn button: {analyzebtn_match.group()[:300]}")

    # Check if button is inside label
    btn_in_label = re.search(r'<label[^>]*>.*?<button[^>]*class=["\'][^"\']*analyze-btn[^"\']*["\'][^>]*>', html, re.DOTALL | re.IGNORECASE)
    print(f"\n6. Is .analyze-btn inside a <label>? {bool(btn_in_label)}")

    # Check for addEventListener in HTML (in inline scripts)
    addevent_count = len(re.findall(r'addEventListener', html))
    print(f"\n7. addEventListener calls in HTML: {addevent_count}")

    # Check for .click() calls in HTML
    click_count = len(re.findall(r'\.click\(\)', html))
    print(f"\n8. .click() calls in HTML: {click_count}")

    # Check for fileInput references
    fileinput_refs = re.findall(r'fileInput', html)
    print(f"\n9. 'fileInput' references in HTML: {len(fileinput_refs)}")

    # 6. Parent/ancestor structure of .analyze-btn (via Playwright)
    ancestor_info = page.evaluate(
        """
        () => {
            const btn = document.querySelector('.analyze-btn');
            if (!btn) return null;
            const ancestors = [];
            let el = btn.parentElement;
            while (el) {
                ancestors.push({
                    tag: el.tagName,
                    class: el.className,
                    id: el.id,
                    htmlFor: el.getAttribute ? el.getAttribute('for') : null,
                });
                el = el.parentElement;
            }
            // Check if any ancestor is a label
            const labelAncestor = btn.closest('label');
            return {
                ancestors: ancestors,
                hasLabelAncestor: !!labelAncestor,
                labelAncestorFor: labelAncestor ? labelAncestor.getAttribute('for') : null,
            };
        }
    """
    )
    print(f"\n10. Analyze button ancestors:")
    if ancestor_info:
        for a in ancestor_info["ancestors"]:
            print(f"    <{a['tag']}> class='{a['class']}' id='{a['id']}' for='{a['htmlFor']}'")
        print(f"    Has label ancestor: {ancestor_info['hasLabelAncestor']}")
        if ancestor_info["hasLabelAncestor"]:
            print(f"    Label's 'for' attribute: {ancestor_info['labelAncestorFor']}")

    # 7. Check if any label contains the analyze button
    label_with_btn = page.evaluate(
        """
        () => {
            const labels = document.querySelectorAll('label');
            const results = [];
            for (const lbl of labels) {
                const btn = lbl.querySelector('.analyze-btn');
                if (btn) {
                    results.push({
                        htmlFor: lbl.getAttribute('for'),
                        className: lbl.className,
                    });
                }
            }
            return results;
        }
    """
    )
    print(f"\n11. Labels containing .analyze-btn: {label_with_btn}")

    # 8. Check form structure
    form_info = page.evaluate(
        """
        () => {
            const form = document.querySelector('form');
            if (!form) return null;
            return {
                action: form.getAttribute('action'),
                method: form.getAttribute('method'),
                enctype: form.getAttribute('enctype'),
                children: Array.from(form.children).map(c => c.tagName + '.' + c.className + (c.id ? '#' + c.id : '')),
            };
        }
    """
    )
    print(f"\n12. Form info: {form_info}")

    # Step 5: Perform the EXACT test sequence
    print("\n\n=== EXACT TEST SEQUENCE ===")

    # Reset counters
    file_chooser_events.clear()

    # Click "Choose File"
    print("\nStep 1: Click 'Choose File' label")
    try:
        # Wait for file chooser to appear
        with page.expect_file_chooser() as fc_info:
            page.click('label[for="fileInput"]')
        file_chooser = fc_info.value
        print("File chooser opened (via label click)")

        # Set the DOCX file
        print(f"Step 2: Set file: {SOURCE_DOCX}")
        file_chooser.set_files(SOURCE_DOCX)
        page.wait_for_timeout(1000)

        # Check file input value
        file_count = page.evaluate('() => document.getElementById("fileInput").files.length')
        file_name = page.evaluate('() => document.getElementById("fileInput").files[0]?.name || "none"')
        print(f"  fileInput.files.length: {file_count}")
        print(f"  fileInput.files[0].name: {file_name}")

        # Check displayed filename
        displayed_name = page.evaluate('() => document.querySelector(".file-name").textContent')
        print(f"  .file-name textContent: '{displayed_name}'")

    except Exception as e:
        print(f"Error during file selection: {e}")
        file_count = 0

    # Click "Analyze AI Content"
    print("\nStep 3: Click 'Analyze AI Content'")
    fc_before = len(file_chooser_events)
    nav_before = len(nav_events)

    page.click('.analyze-btn')
    page.wait_for_timeout(5000)

    fc_after = len(file_chooser_events)
    nav_after = len(nav_events)

    print(f"  File chooser events: {fc_after - fc_before}")
    print(f"  Navigation events: {nav_after - nav_before}")
    print(f"  Current URL: {page.url}")

    # Check network requests for POST /upload
    post_upload_reqs = [r for r in network_requests if "upload" in r["url"] and r["method"] == "POST"]
    print(f"  POST /upload requests: {len(post_upload_reqs)}")
    for r in post_upload_reqs:
        print(f"    {r['method']} {r['url']}")

    # Check for console errors
    print(f"\nConsole messages:")
    for msg in console_messages:
        print(f"  {msg}")

    # Check if file chooser opened
    if fc_after > fc_before:
        print("\n>>> FILE CHOOSER OPENED AFTER CLICKING ANALYZE <<<")
    else:
        print("\n>>> No file chooser after clicking Analyze <<<")

    # Dump the full HTML of the upload section for final check
    upload_section_html = page.evaluate(
        """
        () => {
            const section = document.querySelector('.upload-section');
            return section ? section.innerHTML : 'NOT FOUND';
        }
    """
    )
    print(f"\nUpload section HTML ({len(upload_section_html)} chars):")
    print(upload_section_html[:2000])

    browser.close()
    print("\n=== Done ===")
