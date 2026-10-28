# VerifyAI – SIH Project

## About the Project

VerifyAI is a project we developed to make the process of checking institutional documents easier. Manually checking multiple documents can take a lot of time, so our idea is to use Python and AI to help reviewers find differences and missing information.

This is currently a prototype developed for our SIH project.

## Technologies Used

- **Python** – Used to write the main program.
- **Streamlit** – Used to create the web interface.
- **PyMuPDF** – Used to extract text from PDF files.
- **Tesseract OCR** – Used to read text from scanned documents.
- **Gemini AI** – Used to explain the findings in simple language.
- **GitHub** – Used to store our project files.
- **Streamlit Community Cloud** – Used to host our application online.

## How the Project Works

1. The user uploads the documents that need to be checked.
2. The application extracts the text from the uploaded files.
3. It identifies important details such as the institution name, certificate number, course name, approved intake and dates.
4. It compares the extracted details across the available documents.
5. If something is different or missing, the application highlights it for review.
6. The user can ask Gemini AI to explain the findings.
7. Finally, the user can download a report containing the review results.

## How We Hosted the Project

We first developed the application using Python and Streamlit. Then, we uploaded the project files to a GitHub repository.

After that, we connected our GitHub repository to Streamlit Community Cloud and deployed the application. We also configured the required Python packages and added our Gemini API key through Streamlit's Secrets settings.

After deployment, Streamlit provided us with a web link through which other people can access our application using a browser.

## Files in the Project

- `VerifyAI_Final.py` – Main application code.
- `requirements.txt` – Contains the Python libraries required by the application.
- `packages.txt` – Contains the system packages needed for OCR.
- `README_DEPLOY.md` – Contains information about the project and its deployment.

## Current Limitations

This is only a prototype, and there are still things we need to improve.

- The application is not connected to an official government or institutional database.
- OCR may not extract every word correctly from scanned documents.
- AI-generated explanations may sometimes contain mistakes.
- A mismatch does not automatically mean that a document is fraudulent.
- More testing and security improvements are required before using real confidential documents.

## Future Scope

In the future, we would like to improve the accuracy of document extraction, connect the application to authorised reference databases where access is available, and add more verification features.

## Note

For testing and demonstration, we recommend using sample documents containing fictional information rather than real confidential records.
