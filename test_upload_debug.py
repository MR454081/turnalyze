"""Investigate upload page structure to find root cause of file chooser reopening."""
import os
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1280, "height": 1800}).new_page()

    # Login
    page.goto("http://127.0.0.1:5000/")
    page.fill('input[name="email"]', "admin@turnalyze.com")
    page.fill('input[name="password"]', "admin123")
    page.click('form button[type="submit"]')
    page.wait_for_timeout(2000)

    # Go to upload page
    page.goto("http://127.0.0.1:5000/upload")
    page.wait_for_timeout(2000)

    # Check scripts
    scripts = page.evaluate(
        '() => Array.from(document.querySelectorAll("script")).map(s => s.src || "inline")'
    )
    print("Scripts on /upload page:")
    for s in scripts:
        print(f"  {s}")

    # Check HTML structure
    html = page.evaluate("""
        () => {
            const label = document.querySelector('label[for="fileInput"]');
            const btn = document.querySelector('.analyze-btn');
            const input = document.getElementById('fileInput');
            const form = btn ? btn.closest('form') : null;
            return {
                label_exists: !!label,
                btn_exists: !!btn,
                input_exists: !!input,
                input_hidden: input ? input.hasAttribute('hidden') : null,
                input_display: input ? getComputedStyle(input).display : null,
                form_exists: !!form,
                label_contains_btn: label ? label.contains(btn) : null,
                btn_parent_tag: btn ? btn.parentElement.tagName : null,
                btn_parent_class: btn ? btn.parentElement.className : null,
                form_action: form ? form.getAttribute('action') : null,
                form_method: form ? form.getAttribute('method') : null,
                form_enctype: form ? form.getAttribute('enctype') : null,
            };
        }
    """)
    print("\nHTML structure:")
    for k, v in html.items():
        print(f"  {k}: {v}")

    # Check label and button rects for overlap
    label_rect = page.evaluate("""
        () => {
            const r = document.querySelector('label[for="fileInput"]').getBoundingClientRect();
            return {x: r.x, y: r.y, width: r.width, height: r.height};
        }
    """)
    btn_rect = page.evaluate("""
        () => {
            const r = document.querySelector('.analyze-btn').getBoundingClientRect();
            return {x: r.x, y: r.y, width: r.width, height: r.height};
        }
    """)
    print(f"\nLabel rect: {label_rect}")
    print(f"Button rect: {btn_rect}")

    # Check overlap
    if label_rect and btn_rect:
        overlap_x = max(0, min(label_rect["x"] + label_rect["width"], btn_rect["x"] + btn_rect["width"]) - max(label_rect["x"], btn_rect["x"]))
        overlap_y = max(0, min(label_rect["y"] + label_rect["height"], btn_rect["y"] + btn_rect["height"]) - max(label_rect["y"], btn_rect["y"]))
        print(f"Overlap: x={overlap_x}px, y={overlap_y}px")
        if overlap_x > 0 and overlap_y > 0:
            print(">>> LABEL AND BUTTON OVERLAP! <<<")
        else:
            print("No overlap detected")

    # Check if label extends beyond its text content
    label_computed = page.evaluate("""
        () => {
            const lbl = document.querySelector('label[for="fileInput"]');
            const s = getComputedStyle(lbl);
            return {
                width: s.width,
                height: s.height,
                position: s.position,
                display: s.display,
                padding: s.padding,
                margin: s.margin,
                boxSizing: s.boxSizing,
                zIndex: s.zIndex,
                overflow: s.overflow,
            };
        }
    """)
    print(f"\nLabel computed styles: {label_computed}")

    # Check file-name div position
    fname_rect = page.evaluate("""
        () => {
            const r = document.querySelector('.file-name').getBoundingClientRect();
            return {x: r.x, y: r.y, width: r.width, height: r.height};
        }
    """)
    print(f"\nFile-name div rect: {fname_rect}")

    # Check for drag/drop container
    upload_box = page.evaluate("""
        () => {
            const el = document.querySelector('.upload-box');
            if (!el) return null;
            return {
                display: getComputedStyle(el).display,
                cursor: getComputedStyle(el).cursor,
                position: getComputedStyle(el).position,
                hasClickHandler: false,
            };
        }
    """)
    print(f"\nUpload-box styles: {upload_box}")

    # Check all click event listeners
    print("\nChecking for any click handlers on the page...")
    all_elements_with_click = page.evaluate("""
        () => {
            // This only works in Chrome devtools context, but let's try
            const all = document.querySelectorAll('*');
            const results = [];
            for (const el of all) {
                const style = getComputedStyle(el);
                if (style.cursor === 'pointer') {
                    results.push({
                        tag: el.tagName,
                        class: el.className,
                        id: el.id,
                        cursor: style.cursor,
                    });
                }
            }
            return results.slice(0, 20);
        }
    """)
    print("Elements with cursor:pointer:")
    for e in all_elements_with_click:
        print(f"  <{e['tag']}> class='{e['class']}' id='{e['id']}'")

    # Try clicking the analyze button and monitor for file chooser
    print("\n=== Click test ===")
    fc_opened = [False]

    def on_file_chooser(file_chooser):
        fc_opened[0] = True
        print(f"FILE CHOOSER OPENED!")

    page.on("file_chooser", on_file_chooser)

    # First click Choose File
    page.click('label[for="fileInput"]')
    page.wait_for_timeout(500)
    print(f"After clicking 'Choose File': file_chooser_opened={fc_opened[0]}")

    # Reset and click Analyze
    fc_count = [0]
    def on_fc(fc):
        fc_count[0] += 1

    page.remove_listener("file_chooser", on_file_chooser)
    page.on("file_chooser", on_fc)

    page.click('.analyze-btn')
    page.wait_for_timeout(2000)
    print(f"After clicking 'Analyze AI Content': file_chooser_count={fc_count[0]}")

    if fc_count[0] > 0:
        print(">>> BUG REPRODUCED: Analyze button triggered file chooser <<<")
    else:
        print(">>> No file chooser from Analyze button (in Playwright) <<<")

    page.goto("http://127.0.0.1:5000/upload")
    page.wait_for_timeout(1000)

    # Try with file selected first
    print("\n=== Click test with file selected ===")
    fc_count2 = [0]
    def on_fc2(fc):
        fc_count2[0] += 1

    page.remove_listener("file_chooser", on_fc)
    page.on("file_chooser", on_fc2)

    page.click('label[for="fileInput"]')
    page.wait_for_timeout(500)

    # The file chooser should open, set the file
    try:
        fc = page.wait_for_event("file_chooser", timeout=5000)
        print(f"File chooser opened via label click")
    except:
        print("No file chooser event detected")

    # Click Analyze
    page.click('.analyze-btn')
    page.wait_for_timeout(3000)

    if fc_count2[0] > 1:
        print(f">>> BUG REPRODUCED: file chooser opened {fc_count2[0]} times <<<")
    else:
        print(f">>> file chooser opened {fc_count2[0]} times <<<")

    browser.close()
    print("\nDone.")
