# 🔑 TEST CREDENTIALS - For Local Testing Only

## Copy this to your .env file for local testing:

```bash
# Flask Configuration
SECRET_KEY=local-test-secret-key-change-in-production
FLASK_ENV=development

# IntaSend (M-Pesa) - Test Mode
INTASEND_TOKEN=test_token_placeholder
INTASEND_PUBLISHABLE_KEY=test_key_placeholder
INTASEND_TEST_MODE=True

# Stripe - Test Mode (optional for local testing)
STRIPE_SECRET_KEY=sk_test_placeholder
STRIPE_PUBLISHABLE_KEY=pk_test_placeholder
```

---

## ⚠️ IMPORTANT NOTES:

### For Local Testing:
- ✅ These dummy values will work for basic testing
- ✅ FREE CV downloads will work
- ❌ Real payments won't work (need real API keys)
- ❌ Ads won't show (need real AdSense ID)

### What Works Locally:
1. ✅ Landing page
2. ✅ CV builder form
3. ✅ FREE CV download (with watermark)
4. ✅ File converter (all formats)
5. ✅ Template selection
6. ✅ Form validation

### What Needs Real Keys:
1. ❌ M-Pesa payments (need IntaSend keys)
2. ❌ Stripe payments (need Stripe keys)
3. ❌ Google Ads (need AdSense ID)

---

## 🚀 TO TEST PAYMENTS LOCALLY:

### Get IntaSend Test Keys:
1. Sign up: https://intasend.com/account/signup/
2. Go to: https://intasend.com/account/api-keys/
3. Copy TEST keys (start with `ISSecretKey_test_`)
4. Replace in .env:
   ```
   INTASEND_TOKEN=ISSecretKey_test_xxxxx
   INTASEND_PUBLISHABLE_KEY=ISPubKey_test_xxxxx
   INTASEND_TEST_MODE=True
   ```

### Get Stripe Test Keys:
1. Sign up: https://dashboard.stripe.com/register
2. Go to: https://dashboard.stripe.com/test/apikeys
3. Copy TEST keys (start with `sk_test_`)
4. Replace in .env:
   ```
   STRIPE_SECRET_KEY=sk_test_xxxxx
   ```

### Test Payment:
- Use test M-Pesa number: Any Kenyan number
- Use test card: 4242 4242 4242 4242
- Expiry: Any future date
- CVC: Any 3 digits

---

## 📝 QUICK START:

```bash
# 1. Create .env file
copy .env.example .env

# 2. Edit .env with test credentials above

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run app
python app.py

# 5. Open browser
http://localhost:5000
```

---

## ✅ TESTING WORKFLOW:

### Test 1: FREE CV (No API keys needed)
1. Go to /builder
2. Click "Select Free"
3. Fill form
4. Click "Download Free CV"
5. ✅ PDF downloads with watermark

### Test 2: File Converter (No API keys needed)
1. Go to /converter
2. Upload image (JPG/PNG)
3. Select target format
4. Click "Convert"
5. ✅ File converts and downloads

### Test 3: PREMIUM CV (Needs API keys)
1. Get IntaSend/Stripe test keys
2. Add to .env
3. Restart app
4. Go to /builder
5. Click "Select Premium"
6. Fill form
7. Click "Continue to Payment"
8. Test M-Pesa or Card payment
9. ✅ PDF downloads without watermark

---

## 🎯 READY FOR PRODUCTION?

When ready to deploy:

1. **Get LIVE API Keys:**
   - IntaSend LIVE keys (not test)
   - Stripe LIVE keys (not test)
   - Google AdSense Publisher ID

2. **Update .env:**
   ```
   FLASK_ENV=production
   INTASEND_TEST_MODE=False
   INTASEND_TOKEN=ISSecretKey_live_xxxxx
   STRIPE_SECRET_KEY=sk_live_xxxxx
   ```

3. **Deploy:**
   - Railway/Render/Heroku
   - Set environment variables
   - Test with real money!

---

**START TESTING NOW! 🚀**
