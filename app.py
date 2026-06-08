import os
import io
import hashlib
import time
import tempfile
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

try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError):
    WEASYPRINT_AVAILABLE = False
    print("WARNING: WeasyPrint not available - CV generation disabled")

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_ENV") == "production"

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
        print("WARNING: IntaSend not configured - add keys to .env")
except ImportError:
    INTASEND_AVAILABLE = False
    print("WARNING: intasend-python not installed")

# ── Helpers ────────────────────────────────────────────────────────────────────

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
        raise Exception("IntaSend not configured. Add INTASEND_TOKEN and INTASEND_PUBLISHABLE_KEY to .env")
    phone = format_phone(phone)
    response = intasend_service.collect.mpesa_stk_push(
        phone_number=phone,
        email="pay@converterpro.com",
        amount=amount,
        narrative="ConverterPro Premium CV"
    )
    return response


def check_payment_status(checkout_id: str):
    if not INTASEND_AVAILABLE:
        raise Exception("IntaSend not configured.")
    return intasend_service.collect.status(invoice_id=checkout_id)


def generate_pdf(cv_data: dict, template_name: str) -> str:
    if not WEASYPRINT_AVAILABLE:
        raise Exception("PDF generation not available. Install GTK: https://bit.ly/gtk-win")
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
    HTML(string=html_string, base_url=request.host_url).write_pdf(tmp.name)
    return tmp.name


def validate_cv_data(form) -> tuple:
    errors = []
    name     = form.get("name", "").strip()
    title    = form.get("title", "").strip()
    email    = form.get("email", "").strip()
    phone    = form.get("phone", "").strip()
    location = form.get("location", "").strip()
    linkedin = form.get("linkedin", "").strip()
    website  = form.get("website", "").strip()
    summary  = form.get("summary", "").strip()
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
        job_title        = form.get(f"job_title_{i}", "").strip()
        company          = form.get(f"company_{i}", "").strip()
        start            = form.get(f"start_{i}", "").strip()
        end              = form.get(f"end_{i}", "").strip()
        current          = form.get(f"current_{i}") == "on"
        responsibilities = form.get(f"responsibilities_{i}", "").strip()
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
        institution   = form.get(f"institution_{i}", "").strip()
        qualification = form.get(f"qualification_{i}", "").strip()
        field         = form.get(f"field_{i}", "").strip()
        year          = form.get(f"year_{i}", "").strip()
        grade         = form.get(f"grade_{i}", "").strip()
        if institution or qualification:
            education.append({
                "institution": institution, "qualification": qualification,
                "field": field, "year": year, "grade": grade,
            })

    skills_raw = form.get("skills_hidden", "")
    skills = [s.strip() for s in skills_raw.split(",") if s.strip()][:15]

    languages = []
    for i in range(1, 5):
        lang  = form.get(f"lang_{i}", "").strip()
        level = form.get(f"lang_level_{i}", "").strip()
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
    if not cv_data:
        return redirect(url_for("builder"))
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        if not phone:
            return jsonify({"error": "Phone number is required."}), 400
        try:
            response = trigger_stk_push(phone)
            invoice = response.get("invoice") or {}
            checkout_id = invoice.get("invoice_id")
            if not checkout_id:
                return jsonify({"error": "Payment initiation failed: no invoice ID returned."}), 500
            session["checkout_id"] = checkout_id
            session["pay_phone"] = format_phone(phone)
            session.modified = True
            return jsonify({"checkout_id": checkout_id})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return render_template("pay.html", cv=cv_data)


@app.route("/check-payment/<checkout_id>")
def check_payment(checkout_id):
    if checkout_id != session.get("checkout_id"):
        return jsonify({"status": "INVALID"}), 403
    try:
        response = check_payment_status(checkout_id)
        state = response.get("invoice", {}).get("state", "PENDING").upper()
        if state == "COMPLETE":
            phone = session.get("pay_phone", "unknown")
            token = generate_token(phone)
            session["download_token"] = token
            session["token_used"] = False
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
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        filename = f"{cv_data['name'].replace(' ', '_')}_CV.pdf"
        return send_file(
            io.BytesIO(pdf_bytes),
            as_attachment=True,
            download_name=filename,
            mimetype="application/pdf",
        )
    except Exception as e:
        return f"<h2>Error generating PDF: {e}</h2>", 500
    finally:
        if pdf_path:
            try:
                os.unlink(pdf_path)
            except OSError:
                pass


@app.route("/download-free")
def download_free():
    cv_data = session.get("cv_data")
    if not cv_data or cv_data.get("tier") != "free":
        return redirect(url_for("builder"))
    cv_data["template"] = "classic"
    pdf_path = None
    try:
        pdf_path = generate_pdf(cv_data, "classic")
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        filename = f"{cv_data['name'].replace(' ', '_')}_CV_Free.pdf"
        return send_file(
            io.BytesIO(pdf_bytes),
            as_attachment=True,
            download_name=filename,
            mimetype="application/pdf",
        )
    except Exception as e:
        return f"<h2>Error generating PDF: {e}</h2>", 500
    finally:
        if pdf_path:
            try:
                os.unlink(pdf_path)
            except OSError:
                pass


@app.route("/stripe-checkout", methods=["POST"])
def stripe_checkout():
    cv_data = session.get("cv_data")
    if not cv_data:
        return jsonify({"error": "No CV data found."}), 400
    try:
        import stripe
    except ImportError:
        return jsonify({"error": "Stripe library not installed. Run: pip install stripe"}), 500
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe.api_key:
        return jsonify({"error": "Stripe not configured. Add STRIPE_SECRET_KEY to .env"}), 500
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": "ConverterPro Premium CV",
                        "description": "Professional PDF CV - Instant Download",
                    },
                    "unit_amount": 50,
                },
                "quantity": 1,
            }],
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
    try:
        import stripe
    except ImportError:
        return redirect(url_for("pay"))
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe.api_key:
        return redirect(url_for("pay"))
    try:
        checkout_session = stripe.checkout.Session.retrieve(stripe_session_id)
        if checkout_session.payment_status == "paid":
            identifier = (
                checkout_session.customer_details.email
                if checkout_session.customer_details
                else "stripe_user"
            )
            token = generate_token(identifier or "stripe_user")
            session["download_token"] = token
            session["token_used"] = False
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


@app.route("/convert", methods=["POST"])
def convert():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    uploaded = request.files["file"]
    output_format = request.form.get("output_format", "").lower().strip()

    if not uploaded.filename:
        return jsonify({"error": "No file selected"}), 400
    if not output_format:
        return jsonify({"error": "No output format selected"}), 400

    input_ext = os.path.splitext(uploaded.filename)[1]
    tmp_input_path = None
    output_path    = None
    merge_paths    = []

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=input_ext) as tmp_input:
            tmp_input_path = tmp_input.name
        uploaded.save(tmp_input_path)

        if output_format == 'merge' and 'mergeFiles' in request.files:
            for f in request.files.getlist('mergeFiles'):
                if f.filename:
                    merge_tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
                    merge_tmp.close()
                    f.save(merge_tmp.name)
                    merge_paths.append(merge_tmp.name)

        output_path = convert_file(tmp_input_path, output_format, merge_paths=merge_paths)

        with open(output_path, "rb") as f:
            file_bytes = f.read()

        base_name     = os.path.splitext(uploaded.filename)[0]
        download_name = f"{base_name}_merged.pdf" if output_format == 'merge' else f"{base_name}.{output_format}"

        mime_map = {
            "pdf":   "application/pdf",
            "merge": "application/pdf",
            "docx":  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xlsx":  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "txt":   "text/plain",
            "html":  "text/html",
            "md":    "text/markdown",
            "csv":   "text/csv",
            "json":  "application/json",
            "png":   "image/png",
            "jpg":   "image/jpeg",
            "gif":   "image/gif",
            "bmp":   "image/bmp",
            "webp":  "image/webp",
            "tiff":  "image/tiff",
            "ico":   "image/x-icon",
        }
        mime = mime_map.get(output_format, "application/octet-stream")
        return send_file(
            io.BytesIO(file_bytes),
            mimetype=mime,
            as_attachment=True,
            download_name=download_name,
        )

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Conversion failed: {str(e)}"}), 500
    finally:
        for path in [tmp_input_path, output_path] + merge_paths:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass


# ── AI Features ────────────────────────────────────────────────────────────────

@app.route("/ats-check", methods=["GET", "POST"])
def ats_check():
    cv_data = session.get("cv_data")
    result  = None
    if request.method == "POST":
        if not cv_data:
            cv_data = {
                "name":       request.form.get("name", ""),
                "title":      request.form.get("title", ""),
                "email":      request.form.get("email", ""),
                "phone":      request.form.get("phone", ""),
                "location":   request.form.get("location", ""),
                "linkedin":   request.form.get("linkedin", ""),
                "summary":    request.form.get("summary", ""),
                "experience": [],
                "education":  [],
                "skills":     [s.strip() for s in request.form.get("skills_hidden", "").split(",") if s.strip()],
            }
        job_description = request.form.get("job_description", "")
        result = check_ats_score(cv_data, job_description)
    return render_template("ats_check.html", result=result, cv=cv_data)


@app.route("/cover-letter", methods=["GET", "POST"])
def cover_letter():
    cv_data = session.get("cv_data")
    letter  = None
    error   = None
    if request.method == "POST":
        if not cv_data:
            error = "No CV data found. Please build your CV first."
        else:
            job_title = request.form.get("job_title", "").strip()
            company   = request.form.get("company", "").strip()
            try:
                letter = generate_cover_letter(cv_data, job_title, company)
            except Exception as e:
                error = str(e)
    return render_template("cover_letter.html", letter=letter, error=error, cv=cv_data)


@app.route("/parse-resume", methods=["POST"])
def parse_resume_route():
    if "resume" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    uploaded = request.files["resume"]
    if not uploaded.filename:
        return jsonify({"error": "No file selected"}), 400
    ext = os.path.splitext(uploaded.filename)[1].lower()
    if ext not in (".pdf", ".docx", ".txt"):
        return jsonify({"error": "Only PDF, DOCX, and TXT files are supported"}), 400
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp_path = tmp.name
        uploaded.save(tmp_path)
        parsed = parse_resume(tmp_path)
        return jsonify({"success": True, "data": parsed})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@app.route("/ai-enhance", methods=["POST"])
def ai_enhance():
    cv_data = session.get("cv_data")
    if not cv_data:
        return jsonify({"error": "No CV data found. Build your CV first."}), 400
    if not OPENAI_AVAILABLE:
        return jsonify({"error": "OpenAI not installed. Run: pip install openai"}), 500
    if not os.getenv("OPENAI_API_KEY"):
        return jsonify({"error": "OPENAI_API_KEY not set in .env"}), 500
    try:
        enhanced = enhance_summary(cv_data)
        session["cv_data"] = enhanced
        session.modified = True
        return jsonify({
            "success":    True,
            "summary":    enhanced.get("summary", ""),
            "experience": [e.get("responsibilities", "") for e in enhanced.get("experience", [])],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/email-cv", methods=["POST"])
def email_cv_route():
    cv_data = session.get("cv_data")
    if not cv_data:
        return jsonify({"error": "No CV data found."}), 400
    to_email = request.form.get("email", "").strip()
    if not to_email or "@" not in to_email:
        return jsonify({"error": "Valid email address required."}), 400
    template_name = cv_data.get("template", "classic")
    pdf_path = None
    try:
        pdf_path = generate_pdf(cv_data, template_name)
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        ok = email_cv(to_email, pdf_bytes, cv_data.get("name", "User"))
        if ok:
            return jsonify({"success": True})
        return jsonify({"error": "Email sending failed. Check SENDGRID_API_KEY."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if pdf_path:
            try:
                os.unlink(pdf_path)
            except OSError:
                pass


@app.route("/feature-status")
def feature_status_route():
    return jsonify(feature_status())


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)