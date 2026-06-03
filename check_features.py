"""
Quick test to see what works without GTK
"""
import sys

print("=" * 50)
print("CONVERTERPRO - TESTING WHAT WORKS")
print("=" * 50)
print()

# Test 1: Flask
try:
    from flask import Flask
    print("[OK] Flask installed")
except ImportError:
    print("[FAIL] Flask not installed")
    sys.exit(1)

# Test 2: File Converter dependencies
try:
    from PIL import Image
    print("[OK] Pillow (image conversion) installed")
except ImportError:
    print("[FAIL] Pillow not installed")

try:
    import pandas
    print("[OK] Pandas (spreadsheet conversion) installed")
except ImportError:
    print("[FAIL] Pandas not installed")

# Test 3: WeasyPrint (PDF generation)
try:
    from weasyprint import HTML
    print("[OK] WeasyPrint available - CV generation ENABLED")
    weasyprint_ok = True
except (ImportError, OSError) as e:
    print("[SKIP] WeasyPrint not available - CV generation DISABLED")
    print("       (This is OK for testing File Converter)")
    weasyprint_ok = False

# Test 4: IntaSend
try:
    from intasend import APIService
    print("[OK] IntaSend installed")
except ImportError:
    print("[SKIP] IntaSend not installed - M-Pesa payments DISABLED")

# Test 5: Stripe
try:
    import stripe
    print("[OK] Stripe installed")
except ImportError:
    print("[SKIP] Stripe not installed - Card payments DISABLED")

print()
print("=" * 50)
print("SUMMARY")
print("=" * 50)

if weasyprint_ok:
    print("✓ FULL FEATURES AVAILABLE")
    print("  - CV Builder: YES")
    print("  - File Converter: YES")
else:
    print("✓ LIMITED FEATURES (File Converter Only)")
    print("  - CV Builder: NO (needs GTK)")
    print("  - File Converter: YES")
    print()
    print("To enable CV Builder:")
    print("1. Download GTK:")
    print("   https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases")
    print("2. Install GTK")
    print("3. Restart computer")
    print("4. Run this test again")

print()
print("=" * 50)
print("READY TO START SERVER")
print("=" * 50)
print()
print("Run: python app.py")
print("Then open: http://localhost:5000")
print()
