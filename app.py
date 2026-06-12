import os
import io
import re
import hashlib
import time
import tempfile
import logging
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, send_file, abort
)
from dotenv import load_dotenv
from converter_utils import convert_file
from ai_features import (
    check_ats_score, enhance_summary, generate_cover_letter,
    generate_qr_b64, email_cv, parse_resume, feature_status,
    QR_AVAILABLE, OPENAI_AVAILABLE,
)

# ── Logging (never log sensitive form data) ────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# ── WeasyPrint ─────────────────────────────────────────────────────────────────
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError):
    WEASYPRINT_AVAILABLE = False
    logger.warning("WeasyPrint not available - CV generation disabled")

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_ENV") == "production"
app.config["SESSION_COOKIE_HTTPONLY"] = True

# ── HIGH #1: CSRF Protection via flask-wtf ────────────────────────────────────
try:
    from flask_wtf.csrf import CSRFProtect
    csrf = CSRFProtect(app)
    CSRF_AVAILABLE = True
    logger.info("CSRF protection active")
except ImportError:
    logger.warning("flask-wtf not installed — run: pip install flask-wtf")
    CSRF_AVAILABLE = False

# ── CRITICAL #1: Max upload size — 15MB hard limit ────────────────────────────
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024  # 15MB

# ── CRITICAL #2: Security headers via flask-talisman ─────────────────────────
try:
    from flask_talisman import Talisman
    IS_PROD = os.getenv("FLASK_ENV") == "production"
    Talisman(
        app,
        force_https=IS_PROD,
        strict_transport_security=IS_PROD,
        session_cookie_secure=IS_PROD,
        content_security_policy={
            'default-src': ["'self'"],
            'script-src':  ["'self'", "'unsafe-inline'", "https://pagead2.googlesyndication.com",
                            "https://www.googletagmanager.com", "https://cdnjs.cloudflare.com"],
            'style-src':   ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
            'font-src':    ["'self'", "https://fonts.gstatic.com"],
            'img-src':     ["'self'", "data:", "https:"],
            'connect-src': ["'self'"],
            'frame-src':   ["'none'"],
        },
        x_content_type_options=True,
        x_xss_protection=True,
        referrer_policy='strict-origin-when-cross-origin',
    )
    logger.info("Talisman security headers active")
except ImportError:
    logger.warning("flask-talisman not installed — run: pip install flask-talisman")

# ── CRITICAL #3: Rate limiting ────────────────────────────────────────────────
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "60 per hour"],
        storage_uri="memory://",
    )
    LIMITER_AVAILABLE = True
    logger.info("Rate limiting active")
except ImportError:
    limiter = None
    LIMITER_AVAILABLE = False
    logger.warning("flask-limiter not installed — run: pip install flask-limiter")

# ── CRITICAL #4: Real file type validation ────────────────────────────────────
try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False
    logger.warning("python-magic not installed — run: pip install python-magic-bin")

# Allowed MIME types per extension
ALLOWED_MIME_MAP = {
    '.pdf':  ['application/pdf'],
    '.docx': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document',
              'application/zip'],
    '.xlsx': ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
              'application/zip'],
    '.txt':  ['text/plain'],
    '.html': ['text/html'],
    '.md':   ['text/plain', 'text/markdown'],
    '.csv':  ['text/plain', 'text/csv'],
    '.json': ['application/json', 'text/plain'],
    '.jpg':  ['image/jpeg'],
    '.jpeg': ['image/jpeg'],
    '.png':  ['image/png'],
    '.gif':  ['image/gif'],
    '.bmp':  ['image/bmp', 'image/x-bmp'],
    '.webp': ['image/webp'],
    '.tiff': ['image/tiff'],
    '.ico':  ['image/x-icon', 'image/vnd.microsoft.icon'],
    '.xls':  ['application/vnd.ms-excel'],
}

ALLOWED_EXTENSIONS = set(ALLOWED_MIME_MAP.keys())

def validate_file_type(file_path: str, extension: str) -> bool:
    """Validate file content matches its extension using python-magic."""
    if not MAGIC_AVAILABLE:
        return True  # Graceful degradation if magic not installed
    try:
        mime = magic.from_file(file_path, mime=True)
        allowed = ALLOWED_MIME_MAP.get(extension.lower(), [])
        return mime in allowed
    except Exception:
        return True  # Don't block on magic errors

def is_allowed_extension(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS

# ── IntaSend setup ─────────────────────────────────────────────────────────────
try:
    from intasend import APIService
    INTASEND_TOKEN = os.getenv("INTASEND_TOKEN")
    INTASEND_PUBLISHABLE_KEY = os.getenv("INTASEND_PUBLISHABLE_KEY")
    INTASEND_TEST_MODE = os.getenv("INTASEND_TEST_MODE", "False").lower() == "true"
    if INTASEND_TOKEN and INTASEND_PUBLISHABLE_KEY:
        intasend_service = APIService(
            token=INTASEND_TOKEN,
            publishable_key=INTASEND_PUBLISHABLE_KEY,
            test=INTASEND_TEST_MODE
        )
        INTASEND_AVAILABLE = True
    else:
        INTASEND_AVAILABLE = False
        logger.warning("IntaSend not configured - add keys to .env")
except ImportError:
    INTASEND_AVAILABLE = False
    logger.warning("intasend-python not installed")

# ── Error handler for files that are too large ────────────────────────────────
@app.errorhandler(413)
def file_too_large(e):
    return jsonify({"error": "File too large. Maximum size is 15MB."}), 413

# ── Error handler for CSRF failures ────────────────────────────────────────────
@app.errorhandler(400)
def csrf_error(e):
    logger.warning(f"CSRF error: {e}")
    return jsonify({"error": "Security validation failed. Please try again."}), 400

# ── Helpers ────────────────────────────────────────────────────────────────────

def sanitize_text(text: str, max_length: int = 500) -> str:
    """Strip HTML tags and limit length to prevent XSS and injection."""
    text = re.sub(r'<[^>]+>', '', text)
    return text[:max_length].strip()

def format_phone(phone: str) -> str:
    phone = phone.strip().replace(" ", "").replace("+", "").replace("-", "")
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    if not phone.startswith("254"):
        phone = "254" + phone
    return phone

def generate_token(identifier: str) -> str:
    raw = f"{identifier}{time.time()}{os.getenv('SECRET_KEY', 'dev')}"
    return hashlib.sha256(raw.encode()).hexdigest()

def trigger_stk_push(phone: str, amount: int = 50):
    if not INTASEND_AVAILABLE:
        raise Exception("IntaSend not configured.")
    phone = format_phone(phone)
    return intasend_service.collect.mpesa_stk_push(
        phone_number=phone,
        email="pay@converterpro.com",
        amount=amount,
        narrative="ConverterPro Premium CV"
    )

def check_payment_status(checkout_id: str):
    if not INTASEND_AVAILABLE:
        raise Exception("IntaSend not configured.")
    return intasend_service.collect.status(invoice_id=checkout_id)

def generate_pdf(cv_data: dict, template_name: str) -> str:
    if not WEASYPRINT_AVAILABLE:
        raise Exception("PDF generation not available.")
    html_string = render_template(f"resumes/{template_name}.html", cv=cv_data)
    if cv_data.get("tier") == "free":
        watermark = (
            '<div style="position:fixed;bottom:10px;right:10px;'
            'font-size:9pt;color:#bbb;opacity:0.8;font-family:Arial">'
            "Created with ConverterPro.com</div>"
        )
        html_string = html_string.replace("</body>", watermark + "</body>")
    if QR_AVAILABLE and cv_data.get("linkedin"):
        try:
            qr_b64 = generate_qr_b64(cv_data["linkedin"])
            qr_tag = f'<img src="data:image/png;base64,{qr_b64}" style="width:80px;height:80px;" alt="LinkedIn QR"/>'
            html_string = html_string.replace("<!-- QR_CODE -->", qr_tag)
        except Exception:
            pass
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.close()
    # HIGH #2: base_url restricted to host only — prevents SSRF via WeasyPrint
    HTML(string=html_string, base_url=request.host_url).write_pdf(tmp.name)
    return tmp.name

def validate_cv_data(form) -> tuple:
    errors = []
    name     = sanitize_text(form.get("name", ""), 100)
    title    = sanitize_text(form.get("title", ""), 100)
    email    = sanitize_text(form.get("email", ""), 200)
    phone    = sanitize_text(form.get("phone", ""), 20)
    location = sanitize_text(form.get("location", ""), 100)
    linkedin = sanitize_text(form.get("linkedin", ""), 200)
    website  = sanitize_text(form.get("website", ""), 200)
    summary  = sanitize_text(form.get("summary", ""), 2000)
    template = form.get("template", "classic").strip()
    tier     = form.get("tier", "free").strip()

    if not name:     errors.append("Full name is required.")
    if not title:    errors.append("Professional title is required.")
    if not email or "@" not in email: errors.append("A valid email is required.")
    if not phone:    errors.append("Phone number is required.")
    if not location: errors.append("City is required.")

    if tier == "free":
        template = "classic"
    valid_templates = ("classic", "modern", "minimal", "executive", "creative", "tech")
    if template not in valid_templates:
        template = "classic"

    experience = []
    for i in range(1, 4):
        job_title        = sanitize_text(form.get(f"job_title_{i}", ""), 100)
        company          = sanitize_text(form.get(f"company_{i}", ""), 100)
        start            = sanitize_text(form.get(f"start_{i}", ""), 20)
        end              = sanitize_text(form.get(f"end_{i}", ""), 20)
        current          = form.get(f"current_{i}") == "on"
        responsibilities = sanitize_text(form.get(f"responsibilities_{i}", ""), 1000)
        if i == 1 and not job_title: errors.append("Job title for first experience is required.")
        if i == 1 and not company:   errors.append("Company for first experience is required.")
        if job_title or company:
            experience.append({
                "job_title": job_title, "company": company,
                "start": start, "end": "Present" if current else end,
                "current": current, "responsibilities": responsibilities,
            })

    education = []
    for i in range(1, 3):
        institution   = sanitize_text(form.get(f"institution_{i}", ""), 100)
        qualification = sanitize_text(form.get(f"qualification_{i}", ""), 100)
        field         = sanitize_text(form.get(f"field_{i}", ""), 100)
        year          = sanitize_text(form.get(f"year_{i}", ""), 10)
        grade         = sanitize_text(form.get(f"grade_{i}", ""), 20)
        if institution or qualification:
            education.append({
                "institution": institution, "qualification": qualification,
                "field": field, "year": year, "grade": grade,
            })

    skills_raw = form.get("skills_hidden", "")
    skills = [sanitize_text(s, 50) for s in skills_raw.split(",") if s.strip()][:15]

    languages = []
    for i in range(1, 5):
        lang  = sanitize_text(form.get(f"lang_{i}", ""), 50)
        level = sanitize_text(form.get(f"lang_level_{i}", ""), 30)
        if lang:
            languages.append({"language": lang, "level": level or "Fluent"})

    cv_data = {
        "name": name, "title": title, "email": email,
        "phone": phone, "location": location, "linkedin": linkedin,
        "website": website, "summary": summary, "experience": experience,
        "education": education, "skills": skills, "languages": languages,
        "template": template, "tier": tier,
    }
    return cv_data, errors


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/builder", methods=["GET", "POST"])
def builder():
    if request.method == "POST":
        cv_data, errors = validate_cv_data(request.form)
        if errors:
            return render_template("builder.html", errors=errors, form=request.form)
        session["cv_data"] = cv_data
        session.modified = True
        if cv_data.get("tier") == "free":
            return redirect(url_for("download_free"))
        return redirect(url_for("pay"))
    return render_template("builder.html", errors=[], form={})

@app.route("/pay", methods=["GET", "POST"])
def pay():
    cv_data = session.get("cv_data")
    if not cv_data: return redirect(url_for("builder"))
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        if not phone: return jsonify({"error": "Phone number is required."}), 400
        try:
            response    = trigger_stk_push(phone)
            invoice     = response.get("invoice") or {}
            checkout_id = invoice.get("invoice_id")
            if not checkout_id:
                return jsonify({"error": "Payment initiation failed: no invoice ID returned."}), 500
            session["checkout_id"] = checkout_id
            session["pay_phone"]   = format_phone(phone)
            session.modified = True
            return jsonify({"checkout_id": checkout_id})
        except Exception as e:
            logger.error(f"STK push error: {e}")
            return jsonify({"error": str(e)}), 500
    return render_template("pay.html", cv=cv_data)

@app.route("/check-payment/<checkout_id>")
def check_payment(checkout_id):
    if checkout_id != session.get("checkout_id"):
        return jsonify({"status": "INVALID"}), 403
    try:
        response = check_payment_status(checkout_id)
        state    = response.get("invoice", {}).get("state", "PENDING").upper()
        if state == "COMPLETE":
            phone = session.get("pay_phone", "unknown")
            token = generate_token(phone)
            session["download_token"] = token
            session["token_used"]     = False
            session.modified = True
            return jsonify({"status": "COMPLETE", "redirect": url_for("download", token=token)})
        if state in ("FAILED", "CANCELLED"):
            return jsonify({"status": "FAILED"})
        return jsonify({"status": "PENDING"})
    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)}), 500

@app.route("/download/<token>")
def download(token):
    cv_data      = session.get("cv_data")
    stored_token = session.get("download_token")
    token_used   = session.get("token_used", True)
    if not cv_data:           return redirect(url_for("builder"))
    if token != stored_token: abort(403)
    if token_used:            abort(403)
    session["token_used"] = True
    session.modified = True
    template_name = cv_data.get("template", "classic")
    pdf_path = None
    try:
        pdf_path = generate_pdf(cv_data, template_name)
        with open(pdf_path, "rb") as f: pdf_bytes = f.read()
        filename = f"{cv_data['name'].replace(' ', '_')}_CV.pdf"
        return send_file(io.BytesIO(pdf_bytes), as_attachment=True, download_name=filename, mimetype="application/pdf")
    except Exception as e:
        logger.error(f"PDF generation error: {e}")
        return f"<h2>Error generating PDF: {e}</h2>", 500
    finally:
        if pdf_path:
            try: os.unlink(pdf_path)
            except OSError: pass

@app.route("/download-free")
def download_free():
    cv_data = session.get("cv_data")
    if not cv_data or cv_data.get("tier") != "free":
        return redirect(url_for("builder"))
    cv_data["template"] = "classic"
    pdf_path = None
    try:
        pdf_path = generate_pdf(cv_data, "classic")
        with open(pdf_path, "rb") as f: pdf_bytes = f.read()
        filename = f"{cv_data['name'].replace(' ', '_')}_CV_Free.pdf"
        return send_file(io.BytesIO(pdf_bytes), as_attachment=True, download_name=filename, mimetype="application/pdf")
    except Exception as e:
        return f"<h2>Error generating PDF: {e}</h2>", 500
    finally:
        if pdf_path:
            try: os.unlink(pdf_path)
            except OSError: pass

@app.route("/stripe-checkout", methods=["POST"])
def stripe_checkout():
    cv_data = session.get("cv_data")
    if not cv_data: return jsonify({"error": "No CV data found."}), 400
    try: import stripe
    except ImportError: return jsonify({"error": "Stripe library not installed."}), 500
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe.api_key: return jsonify({"error": "Stripe not configured."}), 500
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price_data": {"currency": "usd", "product_data": {"name": "ConverterPro Premium CV", "description": "Professional PDF CV - Instant Download"}, "unit_amount": 50}, "quantity": 1}],
            mode="payment",
            success_url=request.host_url + "stripe-success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url + "pay",
        )
        session["stripe_session_id"] = checkout_session.id
        session.modified = True
        return jsonify({"checkout_url": checkout_session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/stripe-success")
def stripe_success():
    stripe_session_id = request.args.get("session_id")
    stored_session_id = session.get("stripe_session_id")
    if not stripe_session_id or stripe_session_id != stored_session_id:
        return redirect(url_for("builder"))
    session.pop("stripe_session_id", None)
    session.modified = True
    try: import stripe
    except ImportError: return redirect(url_for("pay"))
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe.api_key: return redirect(url_for("pay"))
    try:
        checkout_session = stripe.checkout.Session.retrieve(stripe_session_id)
        if checkout_session.payment_status == "paid":
            identifier = checkout_session.customer_details.email if checkout_session.customer_details else "stripe_user"
            token = generate_token(identifier or "stripe_user")
            session["download_token"] = token
            session["token_used"]     = False
            session.modified = True
            return redirect(url_for("download", token=token))
    except Exception:
        pass
    return redirect(url_for("pay"))


# ── File Converter ─────────────────────────────────────────────────────────────

@app.route("/converter")
def converter():
    return render_template("converter.html")

@app.route("/merge")
def merge():
    return render_template("merge.html")

@app.route("/split")
def split():
    return render_template("split.html")

@app.route("/compress")
def compress():
    return render_template("compress.html")

@app.route("/rotate")
def rotate():
    return render_template("rotate.html")

@app.route("/delete-pages")
def delete_pages():
    return render_template("delete_pages.html")

@app.route("/extract-pages")
def extract_pages():
    return render_template("extract_pages.html")

@app.route("/add-watermark")
def add_watermark():
    return render_template("add_watermark.html")


# ── CRITICAL #3 applied: rate limit the convert endpoint ─────────────────────
def _convert_route():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    uploaded      = request.files["file"]
    output_format = request.form.get("output_format", "").lower().strip()

    if not uploaded.filename:
        return jsonify({"error": "No file selected"}), 400
    if not output_format:
        return jsonify({"error": "No output format selected"}), 400

    # CRITICAL #4: Extension whitelist check
    if not is_allowed_extension(uploaded.filename):
        return jsonify({"error": "File type not supported."}), 400

    input_ext      = os.path.splitext(uploaded.filename)[1].lower()
    tmp_input_path = None
    output_path    = None
    merge_paths    = []

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=input_ext) as tmp_input:
            tmp_input_path = tmp_input.name
        uploaded.save(tmp_input_path)

        # CRITICAL #4: Real MIME type validation
        if not validate_file_type(tmp_input_path, input_ext):
            return jsonify({"error": "File content does not match its extension."}), 400

        if output_format == 'merge' and 'mergeFiles' in request.files:
            for f in request.files.getlist('mergeFiles'):
                if f.filename:
                    merge_tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
                    merge_tmp.close()
                    f.save(merge_tmp.name)
                    # Validate each merge file too
                    if not validate_file_type(merge_tmp.name, '.pdf'):
                        os.unlink(merge_tmp.name)
                        return jsonify({"error": f"Merge file is not a valid PDF."}), 400
                    merge_paths.append(merge_tmp.name)

        # Extra params for PDF tools
        if output_format == 'delete_pages':
            page_numbers = request.form.get("page_numbers", "").strip()
            if not page_numbers: return jsonify({"error": "Please specify page numbers to delete"}), 400
            output_path = convert_file(tmp_input_path, output_format, page_numbers=page_numbers)
        elif output_format == 'extract_pages':
            page_numbers = request.form.get("page_numbers", "").strip()
            if not page_numbers: return jsonify({"error": "Please specify page numbers to extract"}), 400
            output_path = convert_file(tmp_input_path, output_format, page_numbers=page_numbers)
        elif output_format == 'add_watermark':
            watermark_text = sanitize_text(request.form.get("watermark_text", "CONFIDENTIAL"), 100)
            output_path = convert_file(tmp_input_path, output_format, watermark_text=watermark_text)
        else:
            output_path = convert_file(tmp_input_path, output_format, merge_paths=merge_paths)

        with open(output_path, "rb") as f:
            file_bytes = f.read()

        base_name = os.path.splitext(uploaded.filename)[0]
        name_map  = {
            'merge':         f"{base_name}_merged.pdf",
            'split':         f"{base_name}_pages.zip",
            'compress':      f"{base_name}_compressed.pdf",
            'rotate_90':     f"{base_name}_rotated_90.pdf",
            'rotate_180':    f"{base_name}_rotated_180.pdf",
            'rotate_270':    f"{base_name}_rotated_270.pdf",
            'delete_pages':  f"{base_name}_deleted.pdf",
            'extract_pages': f"{base_name}_extracted.pdf",
            'add_watermark': f"{base_name}_watermarked.pdf",
        }
        download_name = name_map.get(output_format, f"{base_name}.{output_format}")

        mime_map = {
            "pdf": "application/pdf", "merge": "application/pdf",
            "compress": "application/pdf", "rotate_90": "application/pdf",
            "rotate_180": "application/pdf", "rotate_270": "application/pdf",
            "delete_pages": "application/pdf", "extract_pages": "application/pdf",
            "add_watermark": "application/pdf",
            "split": "application/zip", "zip": "application/zip",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "txt": "text/plain", "html": "text/html", "md": "text/markdown",
            "csv": "text/csv", "json": "application/json",
            "png": "image/png", "jpg": "image/jpeg", "gif": "image/gif",
            "bmp": "image/bmp", "webp": "image/webp", "tiff": "image/tiff",
            "ico": "image/x-icon",
        }
        mime = mime_map.get(output_format, "application/octet-stream")
        return send_file(io.BytesIO(file_bytes), mimetype=mime, as_attachment=True, download_name=download_name)

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        return jsonify({"error": f"Conversion failed: {str(e)}"}), 500
    finally:
        for path in [tmp_input_path, output_path] + merge_paths:
            if path:
                try: os.unlink(path)
                except OSError: pass

# Apply rate limit if available, otherwise register normally
if LIMITER_AVAILABLE:
    convert = app.route("/convert", methods=["POST"])(
        limiter.limit("20 per minute")(
            limiter.limit("100 per hour")(_convert_route)
        )
    )
else:
    convert = app.route("/convert", methods=["POST"])(_convert_route)


# ── AI Features ────────────────────────────────────────────────────────────────

@app.route("/ats-check", methods=["GET", "POST"])
def ats_check():
    cv_data = session.get("cv_data")
    result  = None
    if request.method == "POST":
        if not cv_data:
            cv_data = {
                "name":       sanitize_text(request.form.get("name", ""), 100),
                "title":      sanitize_text(request.form.get("title", ""), 100),
                "email":      sanitize_text(request.form.get("email", ""), 200),
                "phone":      sanitize_text(request.form.get("phone", ""), 20),
                "location":   sanitize_text(request.form.get("location", ""), 100),
                "linkedin":   sanitize_text(request.form.get("linkedin", ""), 200),
                "summary":    sanitize_text(request.form.get("summary", ""), 2000),
                "experience": [], "education": [],
                "skills": [sanitize_text(s, 50) for s in request.form.get("skills_hidden", "").split(",") if s.strip()],
            }
        job_description = sanitize_text(request.form.get("job_description", ""), 5000)
        result = check_ats_score(cv_data, job_description)
    return render_template("ats_check.html", result=result, cv=cv_data, has_cv=bool(cv_data))

@app.route("/cover-letter", methods=["GET", "POST"])
def cover_letter():
    cv_data = session.get("cv_data")
    letter = error = None
    if request.method == "POST":
        if not cv_data:
            error = "No CV data found. Please build your CV first."
        else:
            job_title = sanitize_text(request.form.get("job_title", ""), 100)
            company   = sanitize_text(request.form.get("company", ""), 100)
            try: letter = generate_cover_letter(cv_data, job_title, company)
            except Exception as e: error = str(e)
    return render_template("cover_letter.html", letter=letter, error=error, cv=cv_data, ai_available=OPENAI_AVAILABLE)

@app.route("/parse-resume", methods=["POST"])
def parse_resume_route():
    if "resume" not in request.files: return jsonify({"error": "No file uploaded"}), 400
    uploaded = request.files["resume"]
    if not uploaded.filename: return jsonify({"error": "No file selected"}), 400
    ext = os.path.splitext(uploaded.filename)[1].lower()
    if ext not in (".pdf", ".docx", ".txt"):
        return jsonify({"error": "Only PDF, DOCX, and TXT files are supported"}), 400
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp: tmp_path = tmp.name
        uploaded.save(tmp_path)
        if not validate_file_type(tmp_path, ext):
            return jsonify({"error": "File content does not match its extension."}), 400
        parsed = parse_resume(tmp_path)
        return jsonify({"success": True, "data": parsed})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if tmp_path:
            try: os.unlink(tmp_path)
            except OSError: pass

@app.route("/ai-enhance", methods=["POST"])
def ai_enhance():
    cv_data = session.get("cv_data")
    if not cv_data: return jsonify({"error": "No CV data found."}), 400
    if not OPENAI_AVAILABLE: return jsonify({"error": "OpenAI not installed."}), 500
    if not os.getenv("OPENAI_API_KEY"): return jsonify({"error": "OPENAI_API_KEY not set."}), 500
    try:
        enhanced = enhance_summary(cv_data)
        session["cv_data"] = enhanced
        session.modified = True
        return jsonify({"success": True, "summary": enhanced.get("summary", ""), "experience": [e.get("responsibilities", "") for e in enhanced.get("experience", [])]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/email-cv", methods=["POST"])
def email_cv_route():
    cv_data  = session.get("cv_data")
    if not cv_data: return jsonify({"error": "No CV data found."}), 400
    to_email = sanitize_text(request.form.get("email", ""), 200)
    if not to_email or "@" not in to_email: return jsonify({"error": "Valid email address required."}), 400
    template_name = cv_data.get("template", "classic")
    pdf_path = None
    try:
        pdf_path = generate_pdf(cv_data, template_name)
        with open(pdf_path, "rb") as f: pdf_bytes = f.read()
        ok = email_cv(to_email, pdf_bytes, cv_data.get("name", "User"))
        if ok: return jsonify({"success": True})
        return jsonify({"error": "Email sending failed. Check SENDGRID_API_KEY."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if pdf_path:
            try: os.unlink(pdf_path)
            except OSError: pass

@app.route("/feature-status")
def feature_status_route():
    return jsonify(feature_status())

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_ENV") != "production", host="0.0.0.0", port=5000)