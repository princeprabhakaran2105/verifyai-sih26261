import re
import io
import streamlit as st
import fitz
from PIL import Image
import pytesseract
import requests
from datetime import datetime, timezone
import uuid
import sqlite3
from pathlib import Path
def explain_with_cloud_ai(findings_text):
    """Explain pre-calculated findings with Gemini; Python results remain authoritative."""
    api_key = ""
    try:
        api_key = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
    except Exception:
        pass

    if not api_key:
        return (
            "Cloud AI is not configured yet. Add GEMINI_API_KEY in your "
            "Streamlit Community Cloud app's Secrets settings, then restart the app."
        )

    prompt = f"""You assist a human reviewer of institutional documents.
Explain ONLY the already-calculated findings below. Do not recalculate or change statuses.
Explain plausible non-fraud reasons for mismatches, mention OCR/extraction uncertainty,
and recommend checking original documents and an authorised source. Never declare fraud
based only on a mismatch. Keep the explanation concise and clear.

PRE-CALCULATED FINDINGS:
{findings_text}
"""
    try:
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 900},
            },
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
        parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        answer = "\n".join(part.get("text", "") for part in parts if part.get("text"))
        return answer.strip() or "The AI service returned no text. Please try again."
    except requests.Timeout:
        return "The cloud AI request timed out. Try again in a moment."
    except requests.RequestException as exc:
        detail = ""
        if getattr(exc, "response", None) is not None:
            detail = f" (HTTP {exc.response.status_code})"
        return f"Could not contact the cloud AI service{detail}. Check the API key, quota, and connection."
    except (ValueError, KeyError, IndexError, TypeError):
        return "The cloud AI service returned an unexpected response. Try again."

st.set_page_config(page_title="VerifyAI | SIH26261", page_icon="🔎", layout="wide")
st.title("🔎 VerifyAI — Institutional Application Review")
st.caption("SIH26261 prototype • Final integrated review build")
st.info("Demo only. Text matching does not prove document authenticity, and this prototype is not connected to AICTE or government portals.")

st.markdown("""
<style>
    .block-container {padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1500px;}
    [data-testid="stMetric"] {background: rgba(100, 116, 139, 0.10); border: 1px solid rgba(148, 163, 184, 0.22); padding: 14px 16px; border-radius: 14px;}
    [data-testid="stTabs"] button {font-weight: 650; padding-top: 12px; padding-bottom: 12px;}
    div[data-testid="stExpander"] {border-radius: 12px; border-color: rgba(148, 163, 184, 0.28);}
    div.stButton > button, div.stDownloadButton > button {border-radius: 10px; font-weight: 650;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("Demo checklist")
    required_types = st.multiselect(
        "Required document types",
        ["Application form", "Previous approval", "Faculty list", "Infrastructure evidence", "Undertaking"],
        default=["Application form", "Previous approval", "Faculty list"]
    )
    st.caption("Filename-based demo check only; official requirements must be verified separately.")
    st.divider()
    st.subheader("OCR settings")
    ocr_language = st.selectbox("OCR language", ["eng", "tam+eng", "hin+eng"], index=0,
        help="English is usually installed by default. Tamil/Hindi require their Tesseract language packs.")

UPLOAD_TYPES = ["pdf", "txt"]

FIELD_LABELS = {
    "Institution name": ["Institution Name", "College Name", "Institute Name"],
    "Certificate / reference number": ["Certificate Number", "Certificate No", "Registration Number", "Reference Number"],
    "Course name": ["Course Name", "Course", "Programme", "Program"],
    "Approved intake": ["Approved Intake", "Sanctioned Intake", "Approved Seats", "Intake"],
    "Issue date": ["Issue Date", "Date of Issue"],
    "Expiry / validity date": ["Expiry Date", "Expiration Date", "Valid Until", "Validity Date"],
}
DATE_PATTERNS = [
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b",
]

def ocr_page(page, language):
    # Render PDF page at 2x zoom for more reliable OCR.
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(image, lang=language)

def extract_document(upload, language):
    data = upload.getvalue()
    if upload.name.lower().endswith(".txt"):
        return data.decode("utf-8", errors="replace"), "Text file", 0

    text_parts = []
    ocr_pages = 0
    with fitz.open(stream=data, filetype="pdf") as pdf:
        for page_no, page in enumerate(pdf, start=1):
            extracted = page.get_text().strip()
            if len(extracted) >= 20:
                text_parts.append(f"\n[PAGE {page_no} — TEXT EXTRACTION]\n{extracted}")
            else:
                try:
                    recognised = ocr_page(page, language).strip()
                    text_parts.append(f"\n[PAGE {page_no} — OCR]\n{recognised}")
                    ocr_pages += 1
                except Exception as exc:
                    text_parts.append(f"\n[PAGE {page_no} — OCR ERROR: {exc}]\n")
    method = "PDF text extraction + OCR" if ocr_pages else "PDF text extraction"
    if ocr_pages and any("[OCR ERROR:" in part for part in text_parts):
        method = "PDF extraction; OCR partly failed"
    return "\n".join(text_parts).strip(), method, ocr_pages

def extract_field(text, labels):
    for label in labels:
        pattern = r"(?im)^\s*" + re.escape(label) + r"\s*[:\-]\s*(.+?)\s*$"
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()[:200]
    return None

def extract_dates(text):
    found = []
    for pattern in DATE_PATTERNS:
        found.extend(re.findall(pattern, text))
    return list(dict.fromkeys(found))

def normalise(value):
    return re.sub(r"\s+", " ", value).strip().casefold()

def type_from_filename(name):
    n = name.casefold()
    choices = {
        "Application form": ["application", "form"],
        "Previous approval": ["approval", "eoa", "extension"],
        "Faculty list": ["faculty", "staff"],
        "Infrastructure evidence": ["infrastructure", "building", "lab"],
        "Undertaking": ["undertaking", "declaration"],
    }
    for kind, keywords in choices.items():
        if any(k in n for k in keywords):
            return kind
    return None

def compare_documents(docs):
    """Return comparison statuses while keeping missing values visible."""
    results = []
    for field_name in FIELD_LABELS:
        present = [(d["filename"], d["fields"].get(field_name)) for d in docs
                   if d["fields"].get(field_name)]
        missing_files = [d["filename"] for d in docs if not d["fields"].get(field_name)]
        if not present:
            status = "NOT FOUND IN ANY DOCUMENT"
        elif len(present) == 1:
            status = "FOUND IN ONE DOCUMENT"
        elif len({normalise(value) for _, value in present}) > 1:
            status = "MISMATCH — REVIEW"
        elif missing_files:
            status = "MATCH AMONG FOUND VALUES; MISSING IN SOME DOCUMENTS"
        else:
            status = "MATCH"
        results.append({"field": field_name, "status": status,
                        "values": present, "missing_files": missing_files})
    return results


uploads = st.file_uploader("Upload sample documents (PDF or TXT)", type=UPLOAD_TYPES, accept_multiple_files=True)

if not uploads:
    st.markdown("### Quick test")
    st.write("Upload your sample_application.txt and sample_approval.txt files, then try a scanned PDF.")
    st.code("Institution Name: ABC Engineering College\nCertificate Number: DEMO-2026-001\nIssue Date: 2026-06-10\nCourse: Computer Engineering\nApproved Intake: 60")
else:
    docs = []
    with st.spinner("Reading documents and running OCR where needed…"):
        for upload in uploads:
            try:
                text, method, ocr_pages = extract_document(upload, ocr_language)
                error = None
            except Exception as exc:
                text, method, ocr_pages = "", "Failed", 0
                error = str(exc)
            docs.append({
                "filename": upload.name,
                "text": text,
                "method": method,
                "ocr_pages": ocr_pages,
                "error": error,
                "fields": {name: extract_field(text, labels) for name, labels in FIELD_LABELS.items()},
                "dates": extract_dates(text),
                "type": type_from_filename(upload.name),
            })

    # Apply reviewer corrections saved in session state before comparisons are calculated.
    for doc in docs:
        for field_name, raw_value in list(doc["fields"].items()):
            correction_key = "correction_" + re.sub(r"[^a-zA-Z0-9]+", "_", doc["filename"] + "_" + field_name).strip("_").lower()
            if correction_key in st.session_state:
                corrected = str(st.session_state[correction_key]).strip()
                doc["fields"][field_name] = corrected or None
    comparison_results = compare_documents(docs)
    compliance_rows = []
    alteration_rows = []
    trusted_rows = []
    reference_source_name = "No reference dataset uploaded"

    # Report metadata is generated for this review run; it is not an official verification ID.
    report_timestamp = datetime.now().astimezone()
    report_id = "VAI-" + report_timestamp.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6].upper()

    # Prioritise review work using deterministic Python rules, never an AI risk score.
    def review_priority(result):
        status = result["status"]
        if status == "MISMATCH — REVIEW":
            return 0, "HIGH PRIORITY", "Extracted values conflict; verify against original documents."
        if status in {"FOUND IN ONE DOCUMENT", "MATCH AMONG FOUND VALUES; MISSING IN SOME DOCUMENTS"}:
            return 1, "NEEDS ATTENTION", "Information is missing from some documents; confirm whether it is expected."
        if status == "NOT FOUND IN ANY DOCUMENT":
            return 1, "NEEDS ATTENTION", "No value was extracted from any uploaded document."
        return 2, "CONSISTENT", "Available extracted values agree across the uploaded documents."

    prioritised_results = sorted(comparison_results, key=lambda r: (review_priority(r)[0], r["field"].casefold()))

    # High-level review dashboard: counts are calculated by Python, not AI.
    mismatch_count = sum(r["status"] == "MISMATCH — REVIEW" for r in comparison_results)
    missing_count = sum(
        r["status"] in {
            "FOUND IN ONE DOCUMENT",
            "MATCH AMONG FOUND VALUES; MISSING IN SOME DOCUMENTS",
            "NOT FOUND IN ANY DOCUMENT",
        }
        for r in comparison_results
    )
    match_count = sum(r["status"] == "MATCH" for r in comparison_results)
    attention_docs = sum(bool(d["error"]) or not d["text"].strip() for d in docs)

    high_priority_count = sum(review_priority(r)[0] == 0 for r in comparison_results)
    needs_attention_count = sum(review_priority(r)[0] == 1 for r in comparison_results)
    consistent_count = sum(review_priority(r)[0] == 2 for r in comparison_results)

    dashboard_tab, findings_tab, compliance_tab, alteration_tab, trusted_tab, extracted_tab, text_tab, report_tab = st.tabs([
        "📊 Dashboard", "🧭 Findings & Review", "⚖️ Compliance Rules", "🕵️ Alteration Screening",
        "🛡️ Trusted Sources", "📋 Extracted Fields", "📄 Document Text", "📑 Report & AI"
    ])

    with dashboard_tab:
        st.subheader("Verification report summary")
        summary_cols = st.columns(4)
        summary_cols[0].metric("Report reference", report_id)
        summary_cols[1].metric("Documents", len(docs))
        summary_cols[2].metric("Fields flagged", sum(r["status"] != "MATCH" for r in comparison_results))
        summary_cols[3].metric("Generated", report_timestamp.strftime("%H:%M:%S"))
        st.caption(
            f"Generated {report_timestamp.strftime('%Y-%m-%d %Z')} • "
            "Reference ID identifies this demo report only; it is not an official certificate or authentication number."
        )

        st.subheader("Review priority")
        priority_cols = st.columns(3)
        priority_cols[0].metric("High priority", high_priority_count)
        priority_cols[1].metric("Needs attention", needs_attention_count)
        priority_cols[2].metric("Consistent fields", consistent_count)
        st.caption("Priorities are deterministic review guidance based on extracted values, not fraud probabilities or authenticity verification.")
        with st.expander("Open prioritised review queue", expanded=True):
            for result in prioritised_results:
                _, priority_label, reason = review_priority(result)
                if priority_label == "HIGH PRIORITY":
                    st.error(f"{priority_label} · {result['field']} — {result['status']}")
                elif priority_label == "NEEDS ATTENTION":
                    st.warning(f"{priority_label} · {result['field']} — {result['status']}")
                else:
                    st.success(f"{priority_label} · {result['field']} — {result['status']}")
                st.caption(reason)
                for filename, value in result["values"]:
                    st.write(f"- **{filename}:** `{value}`")
                for filename in result["missing_files"]:
                    st.write(f"- **{filename}:** NOT FOUND")

        st.subheader("Review summary")
        metric_cols = st.columns(4)
        metric_cols[0].metric("Documents reviewed", len(docs))
        metric_cols[1].metric("Matching fields", match_count)
        metric_cols[2].metric("Differences to review", mismatch_count)
        metric_cols[3].metric("Missing-field flags", missing_count)

        if attention_docs:
            st.warning(
                f"{attention_docs} document(s) need reading attention because extraction "
                "failed or no readable text was found."
            )
        if mismatch_count:
            st.warning(
                "Review the differences below against the original documents. "
                "A mismatch is a review flag, not proof of fraud."
            )
        elif not attention_docs:
            st.success("No differing extracted values detected in the selected fields.")

        st.success(f"Loaded {len(docs)} document(s).")
        st.subheader("Reading status")
        status_rows = []
        for doc in docs:
            status_rows.append({
                "Document": doc["filename"],
                "Reading method": doc["method"],
                "Pages OCR'd": doc["ocr_pages"],
                "Status": "Read" if doc["text"] and not doc["error"] else "Needs attention",
            })
        st.dataframe(status_rows, use_container_width=True, hide_index=True)
        for doc in docs:
            if doc["error"]:
                st.error(f"{doc['filename']}: {doc['error']}")
            elif not doc["text"].strip():
                st.warning(f"{doc['filename']}: no text recognised. Check scan quality or OCR language packs.")

    with findings_tab:
        st.subheader("Document checklist")
        found_types = {d["type"] for d in docs if d["type"]}
        missing = [kind for kind in required_types if kind not in found_types]
        if missing:
            st.warning("Possible missing document types based on filenames:")
            for kind in missing:
                st.write(f"- {kind}")
        else:
            st.success("All selected checklist labels have matching filenames.")
        st.caption("Filename-based demo only; this does not confirm official completeness.")

        st.subheader("Cross-document comparison")
        for result in comparison_results:
            field_name = result["field"]
            status = result["status"]
            if status == "MATCH":
                st.success(f"{field_name}: {status}")
            elif "MISMATCH" in status or "MISSING" in status or status == "FOUND IN ONE DOCUMENT":
                st.warning(f"{field_name}: {status}")
            else:
                st.info(f"{field_name}: {status}")
            for filename, value in result["values"]:
                st.write(f"- **{filename}:** {value}")
            for filename in result["missing_files"]:
                st.write(f"- **{filename}:** NOT FOUND")

        # Evidence-backed findings: summarize only calculated Python results.
        flagged_results = [
            r for r in prioritised_results
            if r["status"] != "MATCH"
        ]
        st.subheader("Evidence-backed findings")
        if not flagged_results:
            st.success("No non-matching or missing-field results to display.")
        else:
            st.caption(
                "These are review findings based on extracted text, not a fraud verdict. "
                "Check the original documents before making a decision."
            )
            for result in flagged_results:
                with st.expander(f"{result['field']} — {result['status']}", expanded=True):
                    values = result["values"]
                    if values:
                        for filename, value in values:
                            st.markdown(f"- **{filename}:** `{value}`")
                    if result["missing_files"]:
                        st.markdown("**Field not found in:**")
                        for filename in result["missing_files"]:
                            st.markdown(f"- {filename}")
                    if "MISMATCH" in result["status"]:
                        st.info(
                            "Reason: two or more extracted values differ. "
                            "Confirm spelling, institution naming, and source documents."
                        )
                    elif "FOUND IN ONE DOCUMENT" in result["status"]:
                        st.info(
                            "Reason: this field was extracted from only one document. "
                            "Check whether the other documents are expected to contain it."
                        )
                    elif "MISSING" in result["status"] or "NOT FOUND" in result["status"]:
                        st.info(
                            "Reason: this field is missing from one or more documents. "
                            "Absence alone does not establish that a document is invalid."
                        )
                    st.caption("Suggested action: compare the extracted values with the original pages and a trusted source.")

        # Reviewer controls are stored in Streamlit session state for this app session.
        st.subheader("Reviewer decisions")
        st.caption(
            "Record a human review outcome for each flagged field. These decisions are reviewer-entered, "
            "not automatic authentication. They remain in this running session and are included in the report."
        )
        review_options = ["Pending", "Verified by reviewer", "Needs correction"]
        for result in flagged_results:
            field_key = re.sub(r"[^a-zA-Z0-9]+", "_", result["field"]).strip("_").lower()
            status_key = f"review_status_{field_key}"
            note_key = f"review_note_{field_key}"
            if status_key not in st.session_state:
                st.session_state[status_key] = "Pending"
            if note_key not in st.session_state:
                st.session_state[note_key] = ""
            with st.expander(f"Review outcome: {result['field']}", expanded=False):
                st.selectbox(
                    "Reviewer status",
                    review_options,
                    key=status_key,
                    help="Choose an outcome after checking the original document(s).",
                )
                st.text_area(
                    "Reviewer note / reason",
                    key=note_key,
                    placeholder="Example: Checked against the signed approval page; name variation confirmed.",
                    height=80,
                )
        st.caption("Review outcomes are editable and are not a substitute for verification with an authorised source.")

        st.subheader("Dates detected")
        any_dates = False
        for doc in docs:
            if doc["dates"]:
                any_dates = True
                st.write(f"**{doc['filename']}:** " + ", ".join(doc["dates"][:20]))
        if not any_dates:
            st.write("No date-like strings detected.")
        st.caption("Date detection is not an expiry or legal-validity decision.")

    with compliance_tab:
        st.subheader("Regulatory compliance rule checks")
        st.caption("Demo rules only. Replace these with current, approved regulatory requirements before real use.")
        st.info("This engine checks simple configurable rules against extracted fields; it does not determine legal compliance by itself.")
        required_fields = st.multiselect(
            "Fields required for this review", options=list(FIELD_LABELS),
            default=[f for f in ["Institution name", "Certificate number", "Course name", "Approved intake", "Issue date"] if f in FIELD_LABELS],
            key="compliance_required_fields"
        )
        intake_limit = st.number_input("Demo maximum approved intake (set according to the applicable rule)", min_value=1, max_value=10000, value=120, step=10)
        compliance_rows.clear()
        for field in required_fields:
            result = next((r for r in comparison_results if r["field"] == field), None)
            if not result or result["status"] == "NOT FOUND IN ANY DOCUMENT":
                status, explanation = "FAIL — MISSING", "No value was extracted from uploaded documents."
            elif result["status"] in {"MISMATCH — REVIEW", "FOUND IN ONE DOCUMENT", "MATCH AMONG FOUND VALUES; MISSING IN SOME DOCUMENTS"}:
                status, explanation = "REVIEW", "Conflicting or incomplete evidence; a reviewer must decide."
            else:
                status, explanation = "PASS — FIELD PRESENT", "Extracted values agree; this does not prove the value is legally valid."
            compliance_rows.append({"Rule": f"Required field: {field}", "Result": status, "Explanation": explanation})
        intake_result = next((r for r in comparison_results if r["field"] == "Approved intake"), None)
        if intake_result and intake_result["values"]:
            parsed = []
            for _, val in intake_result["values"]:
                m = re.search(r"\d+", str(val).replace(",", ""))
                if m: parsed.append(int(m.group()))
            if parsed:
                if len(set(parsed)) > 1:
                    status, explanation = "REVIEW", "Intake values conflict across documents."
                elif max(parsed) > intake_limit:
                    status, explanation = "REVIEW — LIMIT EXCEEDED", f"Extracted intake {max(parsed)} exceeds the configured demo limit {intake_limit}. Confirm the applicable official rule."
                else:
                    status, explanation = "PASS — WITHIN CONFIGURED LIMIT", f"Extracted intake {max(parsed)} is within the configured demo limit {intake_limit}; confirm the rule is authoritative."
                compliance_rows.append({"Rule": "Approved intake limit", "Result": status, "Explanation": explanation})
        st.dataframe(compliance_rows, use_container_width=True, hide_index=True)

    with alteration_tab:
        st.subheader("Document alteration screening")
        st.warning("These are screening indicators only. Metadata or page differences do not prove tampering; legitimate PDFs can also have these properties.")
        for doc in docs:
            st.markdown(f"**{doc['filename']}**")
            if not doc.get("filename", "").lower().endswith(".pdf"):
                st.caption("Metadata/page-layout screening is available only for PDFs in this prototype.")
                continue
            try:
                raw_pdf = next((u.getvalue() for u in uploads if u.name == doc["filename"]), None)
                if raw_pdf is None:
                    st.caption("Original PDF bytes are unavailable for this check.")
                    continue
                with fitz.open(stream=raw_pdf, filetype="pdf") as pdf:
                    meta = pdf.metadata or {}
                    pages = []
                    for page_no, page in enumerate(pdf, start=1):
                        pages.append({"Page": page_no, "Text characters": len(page.get_text().strip()), "Embedded images": len(page.get_images(full=True)), "Page size": f"{page.rect.width:.0f} × {page.rect.height:.0f}"})
                    st.write({"Pages": len(pdf), "PDF producer": meta.get("producer") or "Not recorded", "Creator": meta.get("creator") or "Not recorded", "Created": meta.get("creationDate") or "Not recorded", "Modified": meta.get("modDate") or "Not recorded"})
                    st.dataframe(pages, use_container_width=True, hide_index=True)
                    indicators = []
                    if meta.get("creationDate") and meta.get("modDate") and meta.get("creationDate") != meta.get("modDate"):
                        indicators.append("Creation/modification timestamps differ")
                    if len({(round(pg.rect.width), round(pg.rect.height)) for pg in pdf}) > 1:
                        indicators.append("Page dimensions vary")
                    alteration_rows.append({"Document": doc["filename"], "Pages": len(pdf), "Producer": meta.get("producer") or "Not recorded", "Creator": meta.get("creator") or "Not recorded", "Indicators": "; ".join(indicators) if indicators else "No listed indicator detected"})
                    if meta.get("creationDate") and meta.get("modDate") and meta.get("creationDate") != meta.get("modDate"):
                        st.warning("Creation and modification timestamps differ. This is a review indicator only.")
                    if len({(round(pg.rect.width), round(pg.rect.height)) for pg in pdf}) > 1:
                        st.warning("Page dimensions vary within this PDF. Check whether that is expected.")
                    else:
                        st.caption("No page-size variation detected; this does not establish that the document is genuine.")
            except Exception as exc:
                st.warning(f"Could not inspect PDF metadata: {exc}")

    with trusted_tab:
        st.subheader("Trusted-source verification")
        st.caption("Upload a reference CSV supplied by an authorised source. This demo compares values only; it does not fetch or certify official records.")
        st.code("institution_name,certificate_number,course_name,approved_intake\nABC Engineering College,DEMO-2026-001,Computer Engineering,60", language="csv")
        ref_file = st.file_uploader("Authorised reference dataset (.csv)", type=["csv"], key="trusted_reference_csv")
        if ref_file is not None:
            try:
                import csv
                reference_rows = list(csv.DictReader(io.StringIO(ref_file.getvalue().decode("utf-8-sig", errors="replace"))))
                reference_source_name = ref_file.name
                st.write(f"Loaded {len(reference_rows)} reference record(s). Confirm the source and date before relying on it.")
                st.dataframe(reference_rows, use_container_width=True, hide_index=True)
                field_map = {"Institution name": "institution_name", "Certificate number": "certificate_number", "Course name": "course_name", "Approved intake": "approved_intake"}
                for field, col_name in field_map.items():
                    extracted = [(d["filename"], d["fields"].get(field)) for d in docs if d["fields"].get(field)]
                    if not extracted:
                        continue
                    st.markdown(f"**{field}**")
                    for filename, value in extracted:
                        matches = [row for row in reference_rows if normalise(str(row.get(col_name, ""))) == normalise(str(value))]
                        if matches:
                            st.success(f"Reference match for {filename}: {value}")
                            trusted_rows.append({"Field": field, "Document": filename, "Extracted value": value, "Reference result": "MATCH IN UPLOADED DATASET"})
                        else:
                            st.warning(f"No exact reference match for {filename}: {value}")
                            trusted_rows.append({"Field": field, "Document": filename, "Extracted value": value, "Reference result": "NO EXACT MATCH IN UPLOADED DATASET"})
                st.caption("No match can mean missing/stale/incomplete reference data or formatting differences; it is not proof of fraud.")
            except Exception as exc:
                st.error(f"Could not read reference CSV: {exc}")
        else:
            st.info("No trusted dataset loaded. Status remains NOT VERIFIED. Do not treat agreement among uploaded documents as official verification.")

    with extracted_tab:
        st.subheader("Extracted fields and manual correction")
        st.caption("If OCR or extraction is wrong, edit the field below. The correction is used after Streamlit reruns; original document text remains unchanged. Record why you corrected it in the reviewer note.")
        for doc in docs:
            with st.expander(f"Correct extracted fields · {doc['filename']}", expanded=False):
                for field_name, raw_value in doc["fields"].items():
                    correction_key = "correction_" + re.sub(r"[^a-zA-Z0-9]+", "_", doc["filename"] + "_" + field_name).strip("_").lower()
                    if correction_key not in st.session_state:
                        st.session_state[correction_key] = raw_value or ""
                    st.text_input(field_name, key=correction_key, help="Leave blank if the field was not found.")
        rows = []
        for doc in docs:
            row = {"Document": doc["filename"], "Reading method": doc["method"]}
            row.update(doc["fields"])
            rows.append(row)
        st.dataframe(rows, use_container_width=True, hide_index=True)
        st.caption("OCR can make mistakes. Confirm extracted values against the original document.")

    with text_tab:
        for doc in docs:
            with st.expander(doc["filename"]):
                st.caption(f"Method: {doc['method']} • Pages OCR'd: {doc['ocr_pages']}")
                st.text(doc["text"][:25000] or "(No text extracted)")

    with report_tab:
        pending_review_count = sum(
            st.session_state.get(
                f"review_status_{re.sub(r'[^a-zA-Z0-9]+', '_', r['field']).strip('_').lower()}",
                "Pending",
            ) == "Pending"
            for r in prioritised_results if r["status"] != "MATCH"
        )
        report = [
            "VERIFYAI — PROFESSIONAL DOCUMENT REVIEW REPORT",
            "SIH26261 prototype | Final integrated review build",
            f"Report reference ID: {report_id}",
            f"Generated at: {report_timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}",
            "",
            "EXECUTIVE SUMMARY",
            f"Documents reviewed: {len(docs)}",
            f"Consistent fields (exact MATCH status): {match_count}",
            f"High-priority mismatches: {mismatch_count}",
            f"Missing/incomplete field flags: {missing_count}",
            f"Flagged fields still Pending reviewer decision: {pending_review_count}",
            f"Documents needing reading attention: {attention_docs}",
            "",
            "IMPORTANT LIMITATIONS",
            "This report compares extracted text only. A mismatch or missing field does not prove fraud.",
            "OCR and text extraction can be wrong. Check the original documents and trusted/authorised sources.",
            "This prototype is not connected to AICTE or government portals and does not authenticate documents.",
            "The report reference ID is generated by this demo and is not an official verification ID.",
            "",
            "DOCUMENT INVENTORY",
        ]
        for doc in docs:
            report.append(f"DOCUMENT: {doc['filename']}")
            report.append(f"Reading method: {doc['method']}; pages OCR'd: {doc['ocr_pages']}")
            for field_name, value in doc["fields"].items():
                report.append(f"  {field_name}: {value or 'NOT FOUND'}")
            report.append(f"  Dates detected: {', '.join(doc['dates']) or 'None'}")
            if doc["error"]:
                report.append(f"  Error: {doc['error']}")
            report.append("")
        report.append("REVIEW PRIORITY QUEUE")
        report.append("Priorities are review guidance, not fraud probabilities or authenticity verification.")
        for result in prioritised_results:
            _, priority_label, reason = review_priority(result)
            report.append(f"{priority_label}: {result['field']} — {result['status']}")
            report.append(f"  Reason: {reason}")
            for filename, value in result["values"]:
                report.append(f"  Evidence: {filename} -> {value}")
            for filename in result["missing_files"]:
                report.append(f"  Missing in: {filename}")
        report.append("")
        report.append("CROSS-DOCUMENT COMPARISON")
        for result in comparison_results:
            report.append(f"{result['field']}: {result['status']}")
            for filename, value in result["values"]:
                report.append(f"  {filename}: {value}")
            for filename in result["missing_files"]:
                report.append(f"  {filename}: NOT FOUND")
        report.append("")
        report.append("EVIDENCE-BASED REVIEW NOTES")
        report.append("Review flags are not proof of fraud. Verify extracted text against original documents.")
        for result in comparison_results:
            if result["status"] == "MATCH":
                continue
            report.append(f"FIELD: {result['field']} — {result['status']}")
            for filename, value in result["values"]:
                report.append(f"  Evidence: {filename} -> {value}")
            for filename in result["missing_files"]:
                report.append(f"  Missing in: {filename}")
            if "MISMATCH" in result["status"]:
                report.append("  Suggested action: compare differing values against the original documents and trusted source.")
            else:
                report.append("  Suggested action: confirm whether this field is expected in each document.")
        report.append("")
        report.append("HUMAN REVIEW DECISIONS")
        report.append("These are reviewer-entered outcomes, not automatic authentication results.")
        flagged_for_review = [r for r in prioritised_results if r["status"] != "MATCH"]
        if not flagged_for_review:
            report.append("No flagged fields required a reviewer outcome.")
        for result in flagged_for_review:
            field_key = re.sub(r"[^a-zA-Z0-9]+", "_", result["field"]).strip("_").lower()
            status_key = f"review_status_{field_key}"
            note_key = f"review_note_{field_key}"
            reviewer_status = st.session_state.get(status_key, "Pending")
            reviewer_note = st.session_state.get(note_key, "").strip()
            report.append(f"{result['field']}: {reviewer_status}")
            report.append(f"  Reviewer note: {reviewer_note or 'None provided'}")
        report.append("")
        report.append("REVIEWER OUTCOME SUMMARY")
        outcome_counts = {option: 0 for option in ["Pending", "Verified by reviewer", "Needs correction"]}
        for result in flagged_for_review:
            field_key = re.sub(r"[^a-zA-Z0-9]+", "_", result["field"]).strip("_").lower()
            outcome = st.session_state.get(f"review_status_{field_key}", "Pending")
            outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
        for outcome, count in outcome_counts.items():
            report.append(f"{outcome}: {count}")
        report.append("")
        report.append("Possible missing filename-based checklist labels: " + (", ".join(missing) if missing else "None"))
        report.append("")
        report.append("END OF REPORT")
        report.append("Generated by VerifyAI SIH26261 demo. Human review and official-source verification remain necessary.")
        st.download_button(
            "Download professional review report (.txt)",
            "\n".join(report),
            f"verifyai_report_{report_id}.txt",
            "text/plain",
        )
        st.markdown("### 🤖 AI-assisted review")
        st.caption(
            "The AI explains calculated results. Python comparison statuses "
            "remain authoritative."
        )

        if st.button("Explain findings with cloud AI"):
            ai_lines = [
                "Explain the following PRE-CALCULATED document comparison results.",
                "Do not recalculate or contradict the statuses.",
                "MATCH means the available values agree.",
                "MISMATCH — REVIEW means the available values differ.",
                "FOUND IN ONE DOCUMENT means only one document contains the field.",
                "MATCH AMONG FOUND VALUES; MISSING IN SOME DOCUMENTS means "
                "the values found agree, but some documents lack the field.",
                "NOT FOUND IN ANY DOCUMENT means no document contains the field.",
                "Missing information is not automatically a mismatch or proof of fraud.",
                "Mention OCR uncertainty where relevant. Recommend checking original documents.",
                "",
                "CALCULATED RESULTS:"
            ]

            for result in comparison_results:
                ai_lines.append(
                    f"\nField: {result['field']}\n"
                    f"Calculated status: {result['status']}"
                )

                for filename, value in result["values"]:
                    ai_lines.append(f"  {filename}: {value}")

                for filename in result["missing_files"]:
                    ai_lines.append(f"  {filename}: NOT FOUND")

            for doc in docs:
                if doc.get("error"):
                    ai_lines.append(
                        f"\nReading error for {doc['filename']}: {doc['error']}"
                    )
                elif not doc["text"].strip():
                    ai_lines.append(
                        f"\nNo readable text in {doc['filename']}; "
                        "results may be incomplete."
                    )

            findings_text = "\n".join(ai_lines)

            with st.spinner("Cloud AI is explaining the calculated findings..."):
                explanation = explain_with_cloud_ai(findings_text)

            st.write(explanation)
            st.caption(
                "AI output may be incorrect. Confirm all findings against "
                "the original documents. A mismatch does not prove fraud."
            )

st.markdown("---")
st.caption("Use synthetic test documents only. Do not upload confidential institutional records or real personal data.")
