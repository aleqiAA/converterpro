# KaziCV - Professional CV Builder with File Converter

A Flask-based web application for creating professional CVs with integrated payment processing (M-Pesa STK Push & Stripe) and a comprehensive file converter.

## Features

### CV Builder
- ✅ Professional CV templates (Classic, Modern, Minimal)
- ✅ ATS-optimized PDF generation
- ✅ M-Pesa STK Push integration
- ✅ Stripe payment integration
- ✅ One-time payment, instant download
- ✅ No account required

### File Converter
- 📷 **Image Conversion**: JPG, PNG, GIF, BMP, WEBP, TIFF, ICO, SVG
- 📄 **Document Conversion**: PDF, DOCX, DOC, TXT, HTML, MD, RTF, ODT
- 📊 **Spreadsheet Conversion**: XLSX, XLS, CSV, JSON
- ⚡ Instant conversion and download
- 🎨 High-quality output

## Installation

### 1. Clone the repository
```bash
git clone <repository-url>
cd kazicv
```

### 2. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Install Pandoc (for document conversion)
- **Windows**: Download from https://pandoc.org/installing.html
- **macOS**: `brew install pandoc`
- **Linux**: `sudo apt-get install pandoc`

### 5. Configure environment variables
```bash
cp .env.example .env
```

Edit `.env` and add your credentials:
- `SECRET_KEY`: Generate a secure random key
- `INTASEND_TOKEN`: Get from https://intasend.com
- `INTASEND_PUBLISHABLE_KEY`: Get from https://intasend.com
- `STRIPE_SECRET_KEY`: Get from https://stripe.com
- `STRIPE_PUBLISHABLE_KEY`: Get from https://stripe.com

### 6. Run the application
```bash
python app.py
```

Visit `http://localhost:5000` in your browser.

## Project Structure

```
kazicv/
├── app.py                  # Main Flask application
├── converter_utils.py      # File conversion utilities
├── requirements.txt        # Python dependencies
├── .env.example           # Environment variables template
├── templates/
│   ├── index.html         # Landing page
│   ├── builder.html       # CV builder form
│   ├── pay.html           # Payment page
│   ├── converter.html     # File converter page
│   └── resumes/           # CV templates
│       ├── classic.html
│       ├── modern.html
│       └── minimal.html
└── static/                # Static assets (if any)
```

## Payment Integration

### M-Pesa STK Push
1. Sign up at https://intasend.com
2. Get your API credentials
3. Add to `.env` file
4. Test mode is enabled by default

### Stripe
1. Sign up at https://stripe.com
2. Get your API keys (test mode)
3. Add to `.env` file
4. For production, use live keys

## File Converter Usage

### Supported Conversions

**Images:**
- Convert between: JPG ↔ PNG ↔ GIF ↔ BMP ↔ WEBP ↔ TIFF ↔ ICO
- Convert to PDF

**Documents:**
- PDF → DOCX, TXT, HTML
- DOCX → PDF, TXT, HTML, MD
- TXT → DOCX, PDF, HTML
- HTML ↔ MD ↔ RTF

**Spreadsheets:**
- XLSX ↔ CSV ↔ JSON
- Export to HTML, TXT

### API Endpoint

```python
POST /convert
Content-Type: multipart/form-data

Parameters:
- file: File to convert
- target_format: Target format (e.g., "pdf", "png", "docx")

Returns: Converted file as download
```

## Development

### Running in Debug Mode
```bash
export FLASK_ENV=development  # Windows: set FLASK_ENV=development
python app.py
```

### Testing Payments
- M-Pesa: Use test credentials from IntaSend
- Stripe: Use test card `4242 4242 4242 4242`

## Deployment

### Environment Variables for Production
```bash
FLASK_ENV=production
SECRET_KEY=<strong-random-key>
INTASEND_TOKEN=<live-token>
STRIPE_SECRET_KEY=<live-key>
```

### Recommended Hosting
- **Heroku**: Easy deployment with Procfile
- **Railway**: Simple Python app hosting
- **DigitalOcean**: App Platform or Droplet
- **AWS**: Elastic Beanstalk or EC2

## Security Notes

- ✅ CSRF protection enabled
- ✅ Secure session cookies
- ✅ One-time download tokens
- ✅ Payment verification
- ✅ File upload validation
- ⚠️ Change `SECRET_KEY` in production
- ⚠️ Use HTTPS in production
- ⚠️ Set proper CORS policies

## Troubleshooting

### WeasyPrint Issues
- Install GTK+ on Windows: https://weasyprint.readthedocs.io/en/stable/install.html
- On Linux: `sudo apt-get install libpango-1.0-0 libpangoft2-1.0-0`

### Pandoc Not Found
- Ensure Pandoc is installed and in PATH
- Restart terminal after installation

### Payment Webhook Issues
- Check IntaSend/Stripe webhook configuration
- Verify callback URLs are accessible
- Check logs for errors

## License

MIT License - feel free to use for personal or commercial projects.

## Support

For issues or questions:
- Open an issue on GitHub
- Email: support@kazicv.com

## Roadmap

- [ ] Add more CV templates
- [ ] Support for cover letters
- [ ] Batch file conversion
- [ ] API for developers
- [ ] Mobile app
- [ ] Multi-language support

---

Built with ❤️ for Kenyan Professionals
