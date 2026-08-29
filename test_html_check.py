"""Check the rendered HTML of /upload for scripts, labels, and structure."""
import re
import requests

session = requests.Session()

# Login
r = session.post("http://127.0.0.1:5000/", data={"email": "admin@turnalyze.com", "password": "admin123"}, allow_redirects=False)
print(f"Login: {r.status_code} -> {r.headers.get('Location', 'no redirect')}")

# Get upload page
r = session.get("http://127.0.0.1:5000/upload")
print(f"GET /upload: {r.status_code}")

# Check for scripts
scripts = re.findall(r'<script[^>]*>(.*?)</script>|<script[^>]*src=["\']([^"\']+)["\']', r.text, re.DOTALL)
print(f"\nScript tags found: {len(scripts)}")
for s in scripts:
    inline = s[0] if s[0] else "(external)"
    src = s[1] if s[1] else "(inline)"
    print(f'  src={src}, inline={inline[:100]}')

# Check for onclick or addEventListener
onclicks = re.findall(r'onclick=["\'][^"\']*["\']', r.text)
addevents = re.findall(r'addEventListener', r.text)
print(f"\nonclick attributes: {len(onclicks)}, addEventListener calls: {len(addevents)}")

# Check labels
labels = re.findall(r'<label[^>]*>.*?</label>', r.text, re.DOTALL)
print(f"\nLabels found: {len(labels)}")
for lbl in labels:
    print(f"  Label: {lbl[:200]}")

# Check form structure
form_match = re.search(r'<form[^>]*>.*?</form>', r.text, re.DOTALL)
if form_match:
    print(f"\nForm HTML:\n{form_match.group()[:800]}")

# Check if the button is inside the label in the raw HTML
btn_in_label = re.search(r'<label[^>]*>.*?<button', r.text, re.DOTALL)
if btn_in_label:
    print(f"\n>>> BUTTON FOUND INSIDE LABEL <<<")
    print(f"Content: {btn_in_label.group()[:200]}")
else:
    print(f"\nButton NOT inside label (good)")

# Check for any unclosed labels before the form
print("\n=== Checking HTML around the form ===")
form_start = r.text.find('<form')
if form_start >= 0:
    # Show 500 chars before the form
    before = r.text[max(0, form_start-500):form_start]
    print(f"Before form (last 500 chars): ...{before[-200:]}")
