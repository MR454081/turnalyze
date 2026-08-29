"""
Debug the upload route using Flask test client.
Import the app directly and test the upload POST endpoint.
"""
import os
import sys
import io

# Add the project directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the Flask app
from app import app, ALLOWED_EXTENSIONS, get_connection

# Check Flask and Werkzeug versions
import flask, werkzeug
print(f"Flask version: {flask.__version__}")
try:
    print(f"Werkzeug version: {werkzeug.__version__}")
except AttributeError:
    import importlib.metadata
    print(f"Werkzeug version: {importlib.metadata.version('werkzeug')}")
print(f"ALLOWED_EXTENSIONS: {ALLOWED_EXTENSIONS}")

# Create a test client
app.config["TESTING"] = True
client = app.test_client()

# Login
login_resp = client.post("/login", data={
    "email": "admin@turnalyze.com",
    "password": "admin123",
}, follow_redirects=True)
print(f"\nLogin: {login_resp.status}")

# Check session
with client.session_transaction() as sess:
    print(f"Session: {dict(sess)}")
    print(f"  'user' in session: {'user' in sess}")
    print(f"  'user_id' in session: {'user_id' in sess}")

# Upload a file
SOURCE_DOCX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "2032AB202683_1.docx")
print(f"\nFile: {SOURCE_DOCX}, size: {os.path.getsize(SOURCE_DOCX)}")

with open(SOURCE_DOCX, "rb") as f:
    resp = client.post(
        "/upload",
        data={"file": (io.BytesIO(f.read()), "2032AB202683_1.docx")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )

print(f"\nUpload response:")
print(f"  Status: {resp.status}")
print(f"  Location: {resp.headers.get('Location', 'N/A')}")

# Check session for flash messages
with client.session_transaction() as sess:
    flashes = sess.get("_flashes", [])
    print(f"  Flash messages: {flashes}")
    print(f"  Session keys: {list(sess.keys())}")

# Also test with the raw requests library
import requests
BASE_URL = "http://10.2.0.2:5000"

session = requests.Session()
# Login
session.post(f"{BASE_URL}/login", data={"email": "admin@turnalyze.com", "password": "admin123"}, allow_redirects=True)

# Check what cookies we have
print(f"\nRequests session cookies: {dict(session.cookies)}")

# Upload
with open(SOURCE_DOCX, "rb") as f:
    file_data = f.read()

# Manually construct the multipart request to see exactly what's being sent
import uuid
boundary = "----WebKitFormBoundary" + uuid.uuid4().hex[:16]

body = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="file"; filename="2032AB202683_1.docx"\r\n'
    f"Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n"
    f"\r\n"
).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

print(f"\nManual multipart request:")
print(f"  Boundary: {boundary}")
print(f"  Body length: {len(body)}")
print(f"  Body header: {body[:200]}")

upload_resp = session.post(
    f"{BASE_URL}/upload",
    data=body,
    headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    },
    allow_redirects=False,
)

print(f"\nManual upload response:")
print(f"  Status: {upload_resp.status_code}")
print(f"  Location: {upload_resp.headers.get('Location', 'N/A')}")

# Check flash messages from the session
with client.session_transaction() as sess:
    flashes2 = sess.get("_flashes", [])
    print(f"  Flash messages: {flashes2}")

# Now test with requests library's files parameter
with open(SOURCE_DOCX, "rb") as f:
    upload_resp2 = session.post(
        f"{BASE_URL}/upload",
        files={"file": ("2032AB202683_1.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        allow_redirects=False,
    )

print(f"\nRequests library upload response:")
print(f"  Status: {upload_resp2.status_code}")
print(f"  Location: {upload_resp2.headers.get('Location', 'N/A')}")

# Check what the requests library actually sent
print(f"\n  Request Content-Type: {upload_resp2.request.headers.get('Content-Type', 'N/A')}")
print(f"  Request body (from prepared request):")
prepared = session.prepare_request(
    requests.Request(
        "POST",
        f"{BASE_URL}/upload",
        files={"file": ("test.docx", file_data[:100], "application/octet-stream")},
        cookies=session.cookies,
    )
)
print(f"  Prepared Content-Type: {prepared.headers.get('Content-Type', 'N/A')}")
if prepared.body:
    if isinstance(prepared.body, bytes):
        print(f"  Prepared body length: {len(prepared.body)}")
        print(f"  Prepared body preview: {prepared.body[:300]}")
    elif hasattr(prepared.body, 'read'):
        data = prepared.body.read()
        print(f"  Prepared body length: {len(data)}")
        print(f"  Prepared body preview: {data[:300]}")
    else:
        print(f"  Prepared body type: {type(prepared.body)}")
        print(f"  Prepared body: {str(prepared.body)[:300]}")
else:
    print(f"  Prepared body: None/empty")
