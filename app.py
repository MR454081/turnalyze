from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, make_response
import os, sqlite3, random, shutil, uuid
from datetime import datetime
from werkzeug.utils import secure_filename
import logging

import mammoth
import fitz
from detector import read_docx, read_pdf, detect_ai
from ai_detector import get_detector
from pdf_converter import convert_docx_to_pdf, highlight_pdf_text, get_pdf_page_count
from report_generator import create_report_pdf

logger = logging.getLogger(__name__)

AI_DISPLAY_MODE = "disabled"


def pdf_has_annotations(pdf_path: str) -> bool:
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            for _ in page.annots():
                return True
        doc.close()
    except Exception:
        pass
    return False


app = Flask(__name__)
app.secret_key = "turnalyze_secret_key_2026"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "turnalyze.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
REPORT_FOLDER = os.path.join(BASE_DIR, "reports")
STATIC_FOLDER = os.path.join(BASE_DIR, "static")
PDF_FOLDER = os.path.join(STATIC_FOLDER, "pdfs")
PAGE_FOLDER = os.path.join(STATIC_FOLDER, "pages")

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["REPORT_FOLDER"] = REPORT_FOLDER
app.config["PDF_FOLDER"] = PDF_FOLDER
app.config["PAGE_FOLDER"] = PAGE_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

for folder in (UPLOAD_FOLDER, REPORT_FOLDER, PDF_FOLDER, PAGE_FOLDER):
    os.makedirs(folder, exist_ok=True)

FREE_PLAN_LIMIT = 4

def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fullname TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        phone TEXT,
        plan TEXT DEFAULT 'Free',
        status TEXT DEFAULT 'active',
        ai_detection_enabled INTEGER DEFAULT 1,
        pdf_download_enabled INTEGER DEFAULT 1,
        is_admin INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reports(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        filename TEXT,
        upload_date TEXT,
        submission_id TEXT,
        pages INTEGER,
        words INTEGER,
        characters INTEGER,
        file_size TEXT,
        ai_score INTEGER,
        human_score INTEGER,
        status TEXT,
        html_content TEXT,
        pdf_path TEXT,
        report_path TEXT
    )
    """)
    conn.commit()

    ensure_schema()

    cursor.execute("SELECT id FROM users WHERE email=?", ("admin@turnalyze.com",))
    if cursor.fetchone() is None:
        cursor.execute(
            "INSERT INTO users(fullname, email, password, plan, status, ai_detection_enabled, pdf_download_enabled, is_admin, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            ("Admin", "admin@turnalyze.com", "admin123", "Pro", "active", 1, 1, 1, datetime.now().strftime("%d %b %Y %I:%M %p GMT+5:30")),
        )
        conn.commit()
    conn.close()

def ensure_schema():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    user_columns = {row[1] for row in cursor.fetchall()}
    for column, definition in [
        ("phone", "ALTER TABLE users ADD COLUMN phone TEXT"),
        ("plan", "ALTER TABLE users ADD COLUMN plan TEXT DEFAULT 'Free'"),
        ("status", "ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'active'"),
        ("ai_detection_enabled", "ALTER TABLE users ADD COLUMN ai_detection_enabled INTEGER DEFAULT 1"),
        ("pdf_download_enabled", "ALTER TABLE users ADD COLUMN pdf_download_enabled INTEGER DEFAULT 1"),
        ("is_admin", "ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0"),
        ("created_at", "ALTER TABLE users ADD COLUMN created_at TEXT"),
    ]:
        if column not in user_columns:
            cursor.execute(definition)
    cursor.execute("PRAGMA table_info(reports)")
    report_columns = {row[1] for row in cursor.fetchall()}
    for column, definition in [
        ("user_id", "ALTER TABLE reports ADD COLUMN user_id INTEGER"),
        ("report_path", "ALTER TABLE reports ADD COLUMN report_path TEXT"),
    ]:
        if column not in report_columns:
            cursor.execute(definition)
    conn.commit()
    conn.close()

initialize_database()
ensure_schema()

ALLOWED_EXTENSIONS = {"pdf", "docx"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def build_pdf_destination(original_name, target_folder=PDF_FOLDER):
    safe_name = secure_filename(os.path.splitext(os.path.basename(original_name))[0]) or "document"
    return os.path.join(target_folder, f"{uuid.uuid4().hex}_{safe_name}.pdf")

def copy_pdf_to_static(source_path, original_name):
    destination = build_pdf_destination(original_name)
    shutil.copy2(source_path, destination)
    return destination

def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def is_admin_user():
    user = get_current_user()
    return bool(user and user["is_admin"])

def build_report_html(report, for_pdf=False):
    ai_score = 0 if AI_DISPLAY_MODE == "disabled" else (report.get("ai_score") or 0)
    return render_template(
        "report.html",
        report_id=report["id"],
        filename=report["filename"],
        submission_date=report["upload_date"],
        upload_date=report["upload_date"],
        download_date=report["upload_date"],
        submission_id=report["submission_id"],
        pages=report.get("pages") or 0,
        words=report.get("words") or 0,
        characters=report.get("characters") or 0,
        file_size=report.get("file_size") or "0 MB",
        ai_score=ai_score,
        human_score=100 - ai_score,
        status=report.get("status") or "Completed",
        html_content=report.get("html_content") or "",
        ai_only=ai_score,
        ai_paraphrased=0,
        page_count=max(3, int(report.get("pages") or 0) + 2),
        pdf_filename=os.path.basename(report.get("pdf_path") or ""),
        pdf_url=url_for("report_preview", report_id=report["id"], _external=False),
        university="Turnalyze University",
        for_pdf=for_pdf,
        report_path=report.get("report_path") or "",
    )

def build_report_pdf(report, text_content=None, highlight_texts=None):
    report_output = os.path.join(app.config["REPORT_FOLDER"], f"report_{report['id']}.pdf")
    highlighted_output = os.path.join(app.config["REPORT_FOLDER"], f"report_{report['id']}_highlighted.pdf")

    original_pdf = report.get("pdf_path") or ""
    highlighted_path = None
    if (
        AI_DISPLAY_MODE != "disabled"
        and original_pdf
        and os.path.exists(original_pdf)
        and highlight_texts
    ):
        highlighted_path = highlight_pdf_text(
            original_pdf,
            highlighted_output,
            ai_score=report.get("ai_score") or 0,
            highlight_texts=highlight_texts or text_content,
        )

    display_ai_score = 0 if AI_DISPLAY_MODE == "disabled" else (report.get("ai_score") or 0)

    create_report_pdf(
        report_output,
        {
            "filename": report.get("filename", "Document"),
            "student_name": report.get(
                "student_name"
            ) or session.get("fullname") or
            report.get("filename", "Document"),
            "document_title": report.get(
                "document_title"
            ) or report.get("filename", "Document"),
            "category": report.get(
                "category",
                "Assignment Submission"
            ),
            "submission_id": report.get("submission_id", "N/A"),
            "upload_date": report.get("upload_date", ""),
            "pages": report.get("pages") or 0,
            "words": report.get("words") or 0,
            "characters": report.get("characters") or 0,
            "file_size": report.get("file_size") or "0 MB",
            "ai_score": display_ai_score,
            "human_score": 100 - display_ai_score,
            "status": report.get("status") or "Completed",
            "ai_only": display_ai_score,
            "ai_paraphrased": 0,
        },
        source_pdf_path=original_pdf,
        highlighted_pdf_path=highlighted_path,
        text_content=text_content,
    )

    return report_output

@app.route("/")
def home():
    return render_template("login.html")

@app.route("/signup")
def signup():
    return render_template("signup.html")

@app.route("/register", methods=["POST"])
def register():
    fullname = request.form["fullname"].strip()
    email = request.form["email"].strip().lower()
    password = request.form["password"]
    confirm = request.form["confirm_password"]
    if password != confirm:
        flash("Passwords do not match.")
        return redirect(url_for("signup"))

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email=?", (email,))
    if cursor.fetchone():
        conn.close()
        flash("Email already exists.")
        return redirect(url_for("signup"))

    cursor.execute(
        "INSERT INTO users(fullname, email, password, plan, status, ai_detection_enabled, pdf_download_enabled, is_admin, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (fullname, email, password, "Free", "active", 1, 1, 0, datetime.now().strftime("%d %b %Y %I:%M %p GMT+5:30")),
    )
    conn.commit()
    conn.close()
    flash("Account created successfully.")
    return redirect(url_for("home"))

@app.route("/login", methods=["POST"])
def login():
    email = request.form["email"].strip().lower()
    password = request.form["password"]
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email=? AND password=?", (email, password))
    user = cursor.fetchone()
    conn.close()
    if user:
        session["user"] = user["email"]
        session["user_id"] = user["id"]
        session["fullname"] = user["fullname"]
        flash("Login successful.")
        return redirect(url_for("dashboard"))
    flash("Invalid Email or Password.")
    return redirect(url_for("home"))

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        flash("Please login first.")
        return redirect(url_for("home"))
    user_id = session.get("user_id")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS total_reports, COALESCE(AVG(ai_score),0) AS avg_ai, COALESCE(AVG(human_score),0) AS avg_human, COALESCE(SUM(words),0) AS total_words FROM reports WHERE user_id=?", (user_id,))
    stats = cursor.fetchone()
    cursor.execute("SELECT id, filename, upload_date, ai_score, human_score, status FROM reports WHERE user_id=? ORDER BY id DESC LIMIT 5", (user_id,))
    recent_reports = cursor.fetchall()
    conn.close()
    return render_template("dashboard.html", fullname=session.get("fullname"), total_reports=stats["total_reports"], avg_ai=round(stats["avg_ai"], 1), avg_human=round(stats["avg_human"], 1), total_words=stats["total_words"], recent_reports=recent_reports)

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.")
    return redirect(url_for("home"))

@app.route("/upload")
def upload_page():
    if "user" not in session:
        flash("Please login first.")
        return redirect(url_for("home"))
    return render_template("upload.html", fullname=session.get("fullname"))

@app.route("/upload", methods=["POST"])
def upload():
    if "user" not in session:
        flash("Please login first.")
        return redirect(url_for("home"))
    if "file" not in request.files:
        flash("Please choose a file.")
        return redirect(url_for("upload_page"))
    file = request.files["file"]
    if file.filename == "":
        flash("No file selected.")
        return redirect(url_for("upload_page"))
    if not allowed_file(file.filename):
        flash("Only PDF and DOCX files are supported.")
        return redirect(url_for("upload_page"))

    filename = os.path.basename(file.filename)
    safe_name = secure_filename(filename) or f"upload_{uuid.uuid4().hex}"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)
    file.save(filepath)

    html_content = ""
    pdf_path = ""
    pdf_pages = 0
    try:
        if filename.lower().endswith(".docx"):
            text = read_docx(filepath)
            with open(filepath, "rb") as docx_file:
                result = mammoth.convert_to_html(docx_file)
            html_content = result.value
            pdf_path = convert_docx_to_pdf(filepath)
            doc = fitz.open(pdf_path)
            pdf_pages = len(doc)
            doc.close()
            pdf_path = copy_pdf_to_static(pdf_path, filename)
        else:
            text = read_pdf(filepath)
            pdf_path = copy_pdf_to_static(filepath, filename)
            pdf_pages = get_pdf_page_count(pdf_path)
    except Exception as exc:
        flash(f"Unable to read document : {exc}")
        return redirect(url_for("upload_page"))

    # Use DeBERTa detector if checkpoint exists, otherwise fall back to heuristic
    try:
        deberta_detector = get_detector()
        if deberta_detector.available:
            detection = deberta_detector.analyze(text)
            logger.info(
                "Using DeBERTa detector. ai_score=%d, mode=%s",
                detection.get("ai_score", 0),
                detection.get("mode", "deberta_prototype"),
            )
        else:
            logger.warning(
                "DeBERTa checkpoint not available at %s. Using heuristic fallback.",
                deberta_detector.checkpoint,
            )
            detection = detect_ai(text)
    except Exception as exc:
        logger.warning(
            "DeBERTa detector failed (%s). Using heuristic fallback.", exc
        )
        detection = detect_ai(text)
    words = detection.get("words", len(text.split()))
    ai_score = detection.get("ai_score", 0)
    human_score = detection.get("human_score", 100 - ai_score)
    status = detection.get("status", "Completed")
    ai_only = detection.get("ai_only", ai_score)
    ai_paraphrased = detection.get("ai_paraphrased", 0)
    characters = len(text)
    highlight_texts = detection.get("highlight_texts") or []
    text_content = detection.get("text_content") or text
    pages = max(1, pdf_pages if pdf_pages > 0 else 1)
    file_size = f"{round(os.path.getsize(filepath) / (1024 * 1024), 2)} MB"
    upload_date = datetime.now().strftime("%d %b %Y %I:%M %p GMT+5:30")
    submission_id = f"trn:oid:::{random.randint(1000,9999)}:{random.randint(100000000,999999999)}"

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO reports(user_id, filename, upload_date, submission_id, pages, words, characters, file_size, ai_score, human_score, status, html_content, pdf_path, report_path)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (session.get("user_id"), filename, upload_date, submission_id, pages, words, characters, file_size, ai_score, human_score, status, html_content, pdf_path, ""))
    conn.commit()
    report_id = cursor.lastrowid
    conn.close()

    report_payload = {"id": report_id, "filename": filename, "upload_date": upload_date, "submission_id": submission_id, "pages": pages, "words": words, "characters": characters, "file_size": file_size, "ai_score": ai_score, "human_score": human_score, "status": status, "html_content": html_content, "pdf_path": pdf_path, "report_path": "", "ai_only": ai_only, "ai_paraphrased": ai_paraphrased, "student_name": "Student", "document_title": filename, "category": "Assignment Submission"}
    report_output = build_report_pdf(report_payload, text_content=text_content, highlight_texts=highlight_texts)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE reports SET report_path=? WHERE id=?", (report_output, report_id))
    conn.commit()
    conn.close()

    return render_template("report.html", report_id=report_id, filename=filename, document_title=filename, student_name=session.get("fullname", filename), category="Assignment Submission", submission_date=upload_date, upload_date=upload_date, download_date=upload_date, submission_id=submission_id, pages=pages, words=words, characters=characters, file_size=file_size, ai_score=ai_score, human_score=human_score, ai_only=ai_only, ai_paraphrased=ai_paraphrased, status=status, html_content=html_content, page_count=max(3, pages + 2), pdf_filename=os.path.basename(pdf_path), pdf_url=url_for("report_preview", report_id=report_id, _external=False), university="Turnalyze University", report_path=report_output)

@app.route("/report/<int:report_id>")
def report_page(report_id):
    if "user" not in session:
        flash("Please login first.")
        return redirect(url_for("home"))
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reports WHERE id=?", (report_id,))
    report = cursor.fetchone()
    conn.close()
    if report is None or (not is_admin_user() and report["user_id"] != session.get("user_id")):
        flash("Report not found.")
        return redirect(url_for("reports"))
    return render_template("report.html", report_id=report["id"], filename=report["filename"], document_title=report["filename"], student_name="Student", category="Assignment Submission", submission_date=report["upload_date"], upload_date=report["upload_date"], download_date=report["upload_date"], submission_id=report["submission_id"], pages=report["pages"], words=report["words"], characters=report["characters"], file_size=report["file_size"], ai_score=0, human_score=100, status=report["status"], html_content=report["html_content"], ai_only=0, ai_paraphrased=0, page_count=max(3, int(report["pages"]) + 2), pdf_filename=os.path.basename(report["pdf_path"]), pdf_url=url_for("report_preview", report_id=report["id"], _external=False), university="Turnalyze University", report_path=report["report_path"])

@app.route("/reports")
def reports():
    if "user" not in session:
        flash("Please login first.")
        return redirect(url_for("home"))
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reports WHERE user_id=? ORDER BY id DESC", (session.get("user_id"),))
    reports_data = cursor.fetchall()
    conn.close()
    return render_template("reports.html", reports=reports_data, fullname=session.get("fullname"))

@app.route("/delete/<int:report_id>")
def delete_report(report_id):
    if "user" not in session:
        return redirect(url_for("home"))
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reports WHERE id=?", (report_id,))
    report = cursor.fetchone()
    if report and (is_admin_user() or report["user_id"] == session.get("user_id")):
        if report["pdf_path"] and os.path.exists(report["pdf_path"]):
            os.remove(report["pdf_path"])
        cursor.execute("DELETE FROM reports WHERE id=?", (report_id,))
        conn.commit()
    conn.close()
    flash("Report deleted successfully.")
    return redirect(url_for("reports"))

@app.route("/report-preview/<int:report_id>")
def report_preview(report_id):
    if "user" not in session:
        return make_response("Unauthorized", 401)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reports WHERE id=?", (report_id,))
    report = cursor.fetchone()
    conn.close()

    if report is None:
        return make_response("Report not found", 404)

    if not is_admin_user() and report["user_id"] != session.get("user_id"):
        return make_response("Forbidden", 403)

    pdf_file = report["report_path"] or ""
    if not pdf_file or not os.path.exists(pdf_file):
        pdf_file = report["pdf_path"] or ""

    if not pdf_file or not os.path.exists(pdf_file):
        return make_response("PDF file not found", 404)

    if AI_DISPLAY_MODE == "disabled" and pdf_has_annotations(pdf_file):
        pdf_file = report["pdf_path"] or ""
        if not pdf_file or not os.path.exists(pdf_file):
            return make_response("PDF file not found", 404)

    return send_file(
        pdf_file,
        mimetype="application/pdf",
        as_attachment=False,
        download_name="original_submission.pdf"
    )

@app.route("/download/<int:report_id>")
def download_report(report_id):
    if "user" not in session:
        return redirect(url_for("home"))

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM reports WHERE id=?",
        (report_id,)
    )

    report = cursor.fetchone()
    conn.close()

    if report is None:
        return make_response("Report not found", 404)

    # Existing ownership/admin protection
    if not is_admin_user() and report["user_id"] != session.get("user_id"):
        return make_response("Forbidden", 403)

    # IMPORTANT:
    # Download the analyzed Turnalyze report, NOT the original submission PDF.
    pdf_path = report["report_path"]

    if not pdf_path:
        return make_response("Report PDF path is empty", 404)

    # Support relative paths as well as absolute paths.
    if not os.path.isabs(pdf_path):
        pdf_path = os.path.abspath(pdf_path)

    if not os.path.isfile(pdf_path):
        return make_response(
            f"Report PDF not found: {pdf_path}",
            404
        )

    if AI_DISPLAY_MODE == "disabled" and pdf_has_annotations(pdf_path):
        try:
            report_data = dict(report)
            report_data["student_name"] = "Student"
            report_data["document_title"] = report_data.get("filename", "Document")
            report_data["category"] = "Assignment Submission"

            pdf_path = build_report_pdf(
                report_data,
                text_content=report_data.get("html_content") or "",
                highlight_texts=None
            )

            pdf_path = os.path.abspath(pdf_path)

            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reports SET report_path=? WHERE id=?",
                (pdf_path, report_id)
            )
            conn.commit()
            conn.close()

        except Exception as e:
            return make_response(
                f"PDF regeneration failed: {e}",
                500
            )

    if not os.path.isfile(pdf_path):
        return make_response(
            f"Report PDF not found: {pdf_path}",
            404
        )

    original_filename = report["filename"]
    base_name = os.path.splitext(original_filename)[0]
    download_filename = base_name + ".pdf"

    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=download_filename
    )
#adhadkhf
@app.route("/get-pdf/<int:report_id>")
def get_pdf(report_id):
    if "user" not in session:
        return redirect(url_for("home"))

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM reports WHERE id=?",
        (report_id,)
    )

    report = cursor.fetchone()
    conn.close()

    if report is None:
        return "Report not found", 404

    if not is_admin_user() and report["user_id"] != session.get("user_id"):
        return "Unauthorized", 403

    pdf_path = report["report_path"] or ""

    if pdf_path:
        pdf_path = os.path.abspath(pdf_path)

    if AI_DISPLAY_MODE == "disabled" and pdf_path and os.path.isfile(pdf_path) and pdf_has_annotations(pdf_path):
        pdf_path = ""

    if not pdf_path or not os.path.isfile(pdf_path):
        pdf_path = os.path.join(
            app.config["REPORT_FOLDER"],
            f"report_{report_id}.pdf"
        )

        pdf_path = os.path.abspath(pdf_path)

    if not os.path.isfile(pdf_path):
        try:
            report_data = dict(report)
            report_data["student_name"] = "Student"
            report_data["document_title"] = report_data.get("filename", "Document")
            report_data["category"] = "Assignment Submission"

            pdf_path = build_report_pdf(
                report_data,
                text_content=report_data.get("html_content") or "",
                highlight_texts=None
            )

            pdf_path = os.path.abspath(pdf_path)

            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                "UPDATE reports SET report_path=? WHERE id=?",
                (pdf_path, report_id)
            )

            conn.commit()
            conn.close()

        except Exception as e:
            print("PDF GENERATION ERROR:", repr(e))
            return f"PDF generation failed: {e}", 500

    if not os.path.isfile(pdf_path):
        return f"PDF not found: {pdf_path}", 404

    print("======================================")
    print("TURNALYZE PDF DOWNLOAD")
    print("Report ID:", report_id)
    print("PDF PATH:", pdf_path)
    print("EXISTS:", os.path.isfile(pdf_path))
    print("SIZE:", os.path.getsize(pdf_path))
    print("ANNOTS:", pdf_has_annotations(pdf_path))
    print("======================================")

    original_filename = report["filename"]
    base_name = os.path.splitext(original_filename)[0]
    download_filename = base_name + ".pdf"

    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=download_filename
    )

@app.route("/history")
def history():
    if "user" not in session:
        flash("Please login first.")
        return redirect(url_for("home"))
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reports WHERE user_id=? ORDER BY id DESC", (session.get("user_id"),))
    reports_data = cursor.fetchall()
    conn.close()
    return render_template("history.html", reports=reports_data, fullname=session.get("fullname"))

@app.route("/account")
def account_page():
    if "user" not in session:
        flash("Please login first.")
        return redirect(url_for("home"))
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT fullname, email FROM users WHERE id=?", (session.get("user_id"),))
    user = cursor.fetchone()
    conn.close()
    return render_template("account.html", fullname=user["fullname"] if user else session.get("fullname"), email=user["email"] if user else session.get("user"))

@app.route("/settings")
def settings_page():
    if "user" not in session:
        flash("Please login first.")
        return redirect(url_for("home"))
    return render_template("settings.html", fullname=session.get("fullname"))

@app.route("/admin")
def admin_dashboard():
    if not is_admin_user():
        flash("Access denied.")
        return redirect(url_for("dashboard"))
    query = request.args.get("q", "").strip()
    conn = get_connection()
    cursor = conn.cursor()
    if query:
        cursor.execute("SELECT u.*, (SELECT COUNT(*) FROM reports r WHERE r.user_id=u.id) AS report_count FROM users u WHERE u.fullname LIKE ? OR u.email LIKE ? OR u.phone LIKE ? ORDER BY u.id DESC", (f"%{query}%", f"%{query}%", f"%{query}%"))
    else:
        cursor.execute("SELECT u.*, (SELECT COUNT(*) FROM reports r WHERE r.user_id=u.id) AS report_count FROM users u ORDER BY u.id DESC")
    users = cursor.fetchall()
    conn.close()
    return render_template("admin.html", users=users, query=query, message="Admin dashboard")

@app.route("/admin/customers/add", methods=["GET", "POST"])
def admin_add_customer():
    if not is_admin_user():
        flash("Access denied.")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        fullname = request.form["fullname"].strip()
        phone = request.form.get("phone", "").strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        plan = request.form.get("plan", "Free")
        conn = get_connection(); cursor = conn.cursor(); cursor.execute("SELECT id FROM users WHERE email=?", (email,))
        if cursor.fetchone():
            conn.close(); flash("Email already exists."); return redirect(url_for("admin_add_customer"))
        if plan == "Free":
            cursor.execute("SELECT COUNT(*) AS count FROM users WHERE plan='Free'")
            if cursor.fetchone()["count"] >= FREE_PLAN_LIMIT:
                conn.close(); flash("Free plan limit reached."); return redirect(url_for("admin_add_customer"))
        cursor.execute("INSERT INTO users(fullname, email, password, phone, plan, status, ai_detection_enabled, pdf_download_enabled, is_admin, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (fullname, email, password, phone, plan, "active", 1, 1, 0, datetime.now().strftime("%d %b %Y %I:%M %p GMT+5:30")))
        conn.commit(); conn.close(); flash("Customer added successfully."); return redirect(url_for("admin_dashboard"))
    return render_template("admin_add_customer.html")

@app.route("/admin/user/<int:user_id>/edit", methods=["GET", "POST"])
def admin_edit_customer(user_id):
    if not is_admin_user():
        flash("Access denied.")
        return redirect(url_for("dashboard"))
    conn = get_connection(); cursor = conn.cursor(); cursor.execute("SELECT * FROM users WHERE id=?", (user_id,)); user = cursor.fetchone(); conn.close()
    if user is None:
        flash("Customer not found.")
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        fullname = request.form["fullname"].strip(); phone = request.form.get("phone", "").strip(); email = request.form["email"].strip().lower(); plan = request.form.get("plan", user["plan"])
        conn = get_connection(); cursor = conn.cursor(); cursor.execute("UPDATE users SET fullname=?, phone=?, email=?, plan=? WHERE id=?", (fullname, phone, email, plan, user_id)); conn.commit(); conn.close(); flash("Customer updated successfully."); return redirect(url_for("admin_dashboard"))
    return render_template("admin_edit_customer.html", user=user)

@app.route("/admin/user/<int:user_id>/toggle-status")
def admin_toggle_status(user_id):
    if not is_admin_user():
        flash("Access denied.")
        return redirect(url_for("dashboard"))
    conn = get_connection(); cursor = conn.cursor(); cursor.execute("SELECT status FROM users WHERE id=?", (user_id,)); user = cursor.fetchone(); conn.close()
    if user:
        new_status = "inactive" if user["status"] == "active" else "active"
        conn = get_connection(); cursor = conn.cursor(); cursor.execute("UPDATE users SET status=? WHERE id=?", (new_status, user_id)); conn.commit(); conn.close()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/user/<int:user_id>/reset-password")
def admin_reset_password(user_id):
    if not is_admin_user():
        flash("Access denied.")
        return redirect(url_for("dashboard"))
    conn = get_connection(); cursor = conn.cursor(); cursor.execute("UPDATE users SET password='password123' WHERE id=?", (user_id,)); conn.commit(); conn.close(); flash("Password reset successfully."); return redirect(url_for("admin_dashboard"))

@app.route("/admin/user/<int:user_id>/assign-plan/<plan>")
def admin_assign_plan(user_id, plan):
    if not is_admin_user():
        flash("Access denied.")
        return redirect(url_for("dashboard"))
    if plan == "Free":
        conn = get_connection(); cursor = conn.cursor(); cursor.execute("SELECT COUNT(*) AS count FROM users WHERE plan='Free'"); free_count = cursor.fetchone()["count"]; conn.close()
        if free_count >= FREE_PLAN_LIMIT:
            flash("Free plan limit reached."); return redirect(url_for("admin_dashboard"))
    conn = get_connection(); cursor = conn.cursor(); cursor.execute("UPDATE users SET plan=? WHERE id=?", (plan, user_id)); conn.commit(); conn.close(); flash("Plan updated successfully."); return redirect(url_for("admin_dashboard"))

@app.route("/admin/user/<int:user_id>/toggle-ai")
def admin_toggle_ai(user_id):
    if not is_admin_user():
        flash("Access denied.")
        return redirect(url_for("dashboard"))
    conn = get_connection(); cursor = conn.cursor(); cursor.execute("SELECT ai_detection_enabled FROM users WHERE id=?", (user_id,)); user = cursor.fetchone(); conn.close()
    if user:
        new_value = 0 if user["ai_detection_enabled"] else 1
        conn = get_connection(); cursor = conn.cursor(); cursor.execute("UPDATE users SET ai_detection_enabled=? WHERE id=?", (new_value, user_id)); conn.commit(); conn.close()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/user/<int:user_id>/toggle-pdf")
def admin_toggle_pdf(user_id):
    if not is_admin_user():
        flash("Access denied.")
        return redirect(url_for("dashboard"))
    conn = get_connection(); cursor = conn.cursor(); cursor.execute("SELECT pdf_download_enabled FROM users WHERE id=?", (user_id,)); user = cursor.fetchone(); conn.close()
    if user:
        new_value = 0 if user["pdf_download_enabled"] else 1
        conn = get_connection(); cursor = conn.cursor(); cursor.execute("UPDATE users SET pdf_download_enabled=? WHERE id=?", (new_value, user_id)); conn.commit(); conn.close()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/user/<int:user_id>/delete")
def admin_delete_user(user_id):
    if not is_admin_user():
        flash("Access denied.")
        return redirect(url_for("dashboard"))
    conn = get_connection(); cursor = conn.cursor(); cursor.execute("DELETE FROM reports WHERE user_id=?", (user_id,)); cursor.execute("DELETE FROM users WHERE id=?", (user_id,)); conn.commit(); conn.close(); flash("Customer deleted successfully."); return redirect(url_for("admin_dashboard"))

@app.errorhandler(404)
def page_not_found(error):
    if "user" in session:
        flash("Page not found.")
        return redirect(url_for("dashboard"))
    return redirect(url_for("home"))

@app.errorhandler(500)
def internal_server_error(error):
    print(error)
    flash("Internal Server Error.")
    if "user" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("home"))

@app.context_processor
def inject_user():
    return {"logged_user": session.get("user"), "logged_name": session.get("fullname")}

@app.route("/health")
def health():
    return {"application": "Turnalyze", "version": "2.0", "status": "Running"}


@app.route("/api/ai-detector/status")
def ai_detector_status():
    try:
        from ai_detector import get_detector
        detector = get_detector()
        return {
            "available": detector.available,
            "model": detector.model_info.get("model_name", "microsoft/deberta-v3-base"),
            "checkpoint": detector.checkpoint,
            "device": detector.device,
            "calibrated": (
                detector._calibrator is not None
                and detector._calibrator.fitted
            ),
        }
    except Exception as exc:
        return {
            "available": False,
            "reason": str(exc),
        }


create_folders = lambda: [os.makedirs(folder, exist_ok=True) for folder in (app.config["UPLOAD_FOLDER"], app.config["REPORT_FOLDER"], app.config["PDF_FOLDER"], app.config["PAGE_FOLDER"])]
create_folders()
initialize_database()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
