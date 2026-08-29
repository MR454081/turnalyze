"""Search dashboard.css for CSS rules that might affect file inputs or labels."""
import re

with open("static/css/dashboard.css") as f:
    css = f.read()

patterns = [
    r'#fileInput',
    r'input\[type.*file',
    r'name.*file',
    r'\[hidden\]',
    r'upload-btn',
    r'label\[for',
    r'analyze-btn',
]

for pat in patterns:
    matches = [(i+1, line.strip()) for i, line in enumerate(css.splitlines()) if re.search(pat, line, re.IGNORECASE)]
    if matches:
        print(f"Pattern: {pat}")
        for lineno, line in matches:
            print(f"  Line {lineno}: {line}")
        print()

# Also specifically check if there's a rule targeting #fileInput
if "#fileInput" in css:
    print(">>> FOUND #fileInput rule in CSS <<<")
else:
    print(">>> No #fileInput rule in CSS <<<")

# Check for any rule that makes labels position absolute
for i, line in enumerate(css.splitlines()):
    if "label" in line.lower() and "position" in line.lower():
        print(f"Label position rule at line {i+1}: {line.strip()}")
