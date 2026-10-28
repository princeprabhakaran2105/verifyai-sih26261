# VerifyAI cloud deployment (Streamlit Community Cloud)

## Files
- `VerifyAI_Final.py`: app entrypoint, updated to use Gemini for optional AI explanations.
- `requirements.txt`: Python dependencies.
- `packages.txt`: Tesseract OCR system packages (English, Tamil, Hindi).
- `.gitignore`: prevents accidentally committing local secrets.

## Deploy
1. Create a GitHub repository, e.g. `verifyai-sih26261`.
2. Upload the four files above to the repository root.
3. Visit https://share.streamlit.io/ and sign in with GitHub.
4. Choose **Create app** and select your repository, branch `main`, and main file `VerifyAI_Final.py`.
5. In app settings / Advanced settings / Secrets, add this line, replacing the placeholder with your actual key:

   `GEMINI_API_KEY = "paste_your_key_here"`

6. Save and deploy. Never put the real key in GitHub or in the Python file.
7. Open the public URL and test with synthetic PDF/TXT files.

Create a Gemini API key at https://aistudio.google.com/ . Check current quotas and billing terms before use.

## Important
- The app sends extracted field comparison results to Gemini only when a user clicks the AI explanation button. Avoid confidential documents; use synthetic test data.
- Python computes the comparison statuses. Gemini only explains them.
- OCR requires the system packages listed in `packages.txt`.
- Reviewer decisions are held in Streamlit session state; this version does not provide durable database audit storage despite unused SQLite imports in the source.
- The compliance limit is a demo-configurable rule, not an official regulatory requirement.
