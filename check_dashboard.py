from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("http://127.0.0.1:5000/")
    page.fill('input[name="email"]', "admin@turnalyze.com")
    page.fill('input[name="password"]', "admin123")
    page.click('form button[type="submit"]')
    page.wait_for_timeout(2000)
    page.goto("http://127.0.0.1:5000/dashboard")
    page.wait_for_timeout(1000)
    html = page.content()
    if "analyzeBtn" in html:
        print("analyzeBtn found in dashboard HTML")
    else:
        print("analyzeBtn NOT found in dashboard HTML")
        import re
        form = re.search(r"<form[^>]*>.*?</form>", html, re.DOTALL)
        if form:
            print("Form HTML:", form.group()[:500])
    browser.close()
