"""Test exact click at button coordinates and form submission."""
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

    # Go to upload
    page.goto("http://127.0.0.1:5000/upload")
    page.wait_for_timeout(1000)

    # Get button bounding box
    btn_box = page.evaluate(
        '() => document.querySelector(".analyze-btn").getBoundingClientRect()'
    )
    print(f"Analyze button box: {btn_box}")

    # Get label bounding box
    label_box = page.evaluate(
        '() => document.querySelector("label[for=fileInput]").getBoundingClientRect()'
    )
    print(f"Choose File label box: {label_box}")

    # Check for ANY event listeners on the page
    print("\nChecking for event listeners...")

    # Check if there's a click handler on the form, upload-box, or body
    # (getEventListeners is Chrome DevTools only, but let's try)
    has_click_form = page.evaluate(
        '() => { const f = document.querySelector("form"); return f ? (f.onclick !== undefined || f.getAttribute("onclick")) : null; }'
    )
    print(f"Form onclick: {has_click_form}")

    # Check for any MutationObserver or event listeners
    listeners_info = page.evaluate(
        """
        () => {
            // Check all elements for inline event handlers
            const all = document.querySelectorAll('*');
            const handlers = [];
            const events = ['onclick', 'onmousedown', 'onmouseup', 'onmouseenter', 'onmouseleave', 'onmouseover', 'onmouseout', 'onfocus', 'onblur'];
            for (const el of all) {
                for (const evt of events) {
                    if (el[evt]) {
                        handlers.push({
                            tag: el.tagName,
                            class: el.className,
                            id: el.id,
                            event: evt,
                            handler: el[evt].toString().substring(0, 100)
                        });
                    }
                }
            }
            return handlers;
        }
    """
    )
    print(f"Inline event handlers found: {len(listeners_info)}")
    for h in listeners_info:
        print(f"  <{h['tag']}>.{h['class']} #{h['id']} {h['event']} = {h['handler']}")

    # Now try clicking the button with mouse at exact coordinates
    file_chooser_events = []

    def track_file_chooser(fc):
        file_chooser_events.append(True)

    page.on("file_chooser", track_file_chooser)

    print("\n=== Clicking Analyze button using page.click() ===")
    page.click('.analyze-btn')
    page.wait_for_timeout(3000)
    print(f"File chooser events: {len(file_chooser_events)}")

    # Re-navigate and try with exact mouse coordinates
    page.goto("http://127.0.0.1:5000/upload")
    page.wait_for_timeout(1000)

    file_chooser_events2 = []

    def track_file_chooser2(fc):
        file_chooser_events2.append(True)

    page.on("file_chooser", track_file_chooser2)

    # Click at the center of the button
    center_x = btn_box["x"] + btn_box["width"] / 2
    center_y = btn_box["y"] + btn_box["height"] / 2
    print(f"\n=== Clicking at button center: ({center_x}, {center_y}) ===")
    page.mouse.click(center_x, center_y)
    page.wait_for_timeout(3000)
    print(f"File chooser events: {len(file_chooser_events2)}")

    # Check if we're still on /upload (form submitted) or redirected
    print(f"Current URL: {page.url}")

    browser.close()
