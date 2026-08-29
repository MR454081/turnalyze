"""Inspect rendered HTML structure for upload page."""
from playwright.sync_api import sync_playwright

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

    # Get ALL label elements
    labels = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('label')).map(l => ({
            htmlFor: l.getAttribute('for'),
            className: l.className,
            text: l.innerText.trim(),
            containsBtn: l.querySelector('button') !== null,
            containsInput: l.querySelector('input') !== null,
            parentTag: l.parentElement.tagName,
        }))
    """
    )
    print("All label elements:")
    for l in labels:
        print(f'  for={l["htmlFor"]}, class={l["className"]}, text="{l["text"]}", containsBtn={l["containsBtn"]}, parent={l["parentTag"]}')

    # Get ALL button elements
    buttons = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('button')).map(b => ({
            type: b.getAttribute('type'),
            className: b.className,
            text: b.innerText.trim(),
            parentTag: b.parentElement.tagName,
            parentClass: b.parentElement.className,
            insideLabel: b.closest('label') !== null,
        }))
    """
    )
    print("\nAll button elements:")
    for b in buttons:
        print(f'  type={b["type"]}, class={b["className"]}, text="{b["text"]}", parent={b["parentTag"]}, insideLabel={b["insideLabel"]}')

    # Get file inputs
    inputs = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('input[type="file"]')).map(i => ({
            id: i.id,
            name: i.name,
            hidden: i.hasAttribute('hidden'),
            display: getComputedStyle(i).display,
            opacity: getComputedStyle(i).opacity,
            position: getComputedStyle(i).position,
        }))
    """
    )
    print("\nFile input elements:")
    for i in inputs:
        print(f'  id={i["id"]}, hidden={i["hidden"]}, display={i["display"]}, opacity={i["opacity"]}, position={i["position"]}')

    # Check for duplicate IDs
    dup_ids = page.evaluate(
        """
        () => {
            const all = document.querySelectorAll('*');
            const idMap = {};
            for (const el of all) {
                if (el.id) {
                    if (!idMap[el.id]) idMap[el.id] = [];
                    idMap[el.id].push(el.tagName);
                }
            }
            return Object.entries(idMap).filter(([k,v]) => v.length > 1);
        }
    """
    )
    print(f"\nDuplicate IDs: {dup_ids}")

    # Check for onclick attributes
    onclick_attrs = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('[onclick]')).map(el => ({
            tag: el.tagName,
            class: el.className,
            id: el.id,
            onclick: el.getAttribute('onclick'),
        }))
    """
    )
    print("\nElements with onclick:")
    if onclick_attrs:
        for el in onclick_attrs:
            print(f'  <{el["tag"]}> onclick="{el["onclick"]}"')
    else:
        print("  None")

    # Check form structure
    form_info = page.evaluate(
        """
        () => {
            const form = document.querySelector('form[action*="/upload"]');
            if (!form) return null;
            return {
                action: form.getAttribute('action'),
                method: form.getAttribute('method'),
                enctype: form.getAttribute('enctype'),
                children: Array.from(form.children).map(c => c.tagName + '.' + c.className),
            };
        }
    """
    )
    print(f"\nForm info: {form_info}")

    browser.close()
