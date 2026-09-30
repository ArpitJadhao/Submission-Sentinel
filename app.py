import json
import os
import tempfile
from pathlib import Path
from fastapi.responses import FileResponse
import ipaddress
from urllib.parse import urlsplit
import asyncio

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from main import guideline_extractor, agent, analyze_paper_pdf


app = FastAPI(title="Submission Sentinel")
analysis_semaphore = asyncio.Semaphore(2)

BASE_DIR = Path(__file__).resolve().parent

@app.get("/")
def home():
    return FileResponse(BASE_DIR / "frontend" / "index.html")


@app.post("/analyze")
async def analyze_paper(
    pdf: UploadFile = File(...),
    submission_url: str = Form(...)
):
    async with analysis_semaphore:
        return await analyze_paper_limited(pdf, submission_url)


async def analyze_paper_limited(
    pdf: UploadFile,
    submission_url: str
):
    # 1. Validate the uploaded PDF
    if not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a PDF file."
        )

    # 2. Read the uploaded file and enforce a 10 MB limit
    file_content = await pdf.read()

    if len(file_content) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="The PDF must be 10 MB or smaller."
        )

    if not file_content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400,
            detail="The uploaded file does not appear to be a valid PDF."
        )

    # 3. Validate the guideline URL
    try:
        parsed_url = urlsplit(submission_url.strip())
        hostname = parsed_url.hostname

        if (
            parsed_url.scheme not in ("http", "https")
            or not hostname
            or parsed_url.username is not None
            or parsed_url.password is not None
        ):
            raise ValueError("Invalid URL")

        hostname = hostname.lower()

        # Reject local hostnames
        if (
            hostname == "localhost"
            or hostname.endswith(".localhost")
            or hostname.endswith(".local")
        ):
            raise ValueError("Local addresses are not allowed")

        # Check whether the hostname is an IP address.
        # Normal domain names are allowed through this check.
        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            ip = None

        # Reject non-public IP addresses
        if ip is not None and not ip.is_global:
            raise ValueError("Non-public IP addresses are not allowed")

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Please enter a valid public HTTP or HTTPS guideline URL."
        )

    # 3. Save the uploaded PDF temporarily
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".pdf",
            delete=False
        ) as temp_file:
            temp_file.write(file_content)
            temp_path = temp_file.name

        # 4. Extract conference requirements
        guideline_response = guideline_extractor.invoke({
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Retrieve and extract all submission requirements "
                        f"from this conference guidelines page: "
                        f"{submission_url}"
                    )
                }
            ]
        })

        requirements_report = guideline_response["structured_response"]

        requirements_json = json.dumps(
            requirements_report.model_dump(),
            indent=2
        )

        # 5. Extract the uploaded paper's content
        paper_content = analyze_paper_pdf.invoke({
            "pdf_path": temp_path
        })

        # 6. Evaluate the paper using your existing agent
        evaluation_prompt = f"""
        Evaluate the research paper against the conference requirements.

        Extracted paper content:
        {paper_content}

        Conference guidelines URL:
        {submission_url}

        Extracted conference requirements:
        {requirements_json}

        Evaluate only requirements applicable to the manuscript itself.
        Do not evaluate presentation, registration, or attendance
        requirements against the PDF.

        Identify the actual paper title from the first page.
        Do not use the PDF filename as the title.

        Follow the compliance evaluation rules in your system prompt.
        Return a structured ComplianceReport.
        """

        evaluation_response = agent.invoke({
            "messages": [
                {
                    "role": "user",
                    "content": evaluation_prompt
                }
            ]
        })

        report = evaluation_response["structured_response"]

        # 7. Calculate compliance status counts
        status_counts = {
            "COMPLIANT": 0,
            "NON-COMPLIANT": 0,
            "PARTIALLY COMPLIANT": 0,
            "UNVERIFIABLE": 0,
        }

        for finding in report.findings:
            status_counts[finding.status] += 1

        # 8. Return the report to the frontend
        return {
            "paper_title": report.paper_title,
            "status_counts": status_counts,
            "total_findings": len(report.findings),
            "findings": [
                finding.model_dump()
                for finding in report.findings
            ],
            "action_items": report.action_items,
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail=(
                "Analysis failed. Check the server terminal for the "
                "underlying error and try again."
            )
        )

    finally:
        # 9. Delete the temporary PDF after processing
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

        await pdf.close()