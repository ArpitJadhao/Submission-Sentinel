import json
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import Literal, Optional
from pydantic import BaseModel, Field

from tools import get_submission_requirements, analyze_paper_pdf

    
class ComplianceFinding(BaseModel):
    requirement_number: Optional[int] = None
    finding_number: int
    category: str
    requirement: str
    guidelines_evidence: str
    paper_evidence: str
    status: Literal[
        "COMPLIANT",
        "NON-COMPLIANT",
        "PARTIALLY COMPLIANT",
        "UNVERIFIABLE"
    ]
    recommendation: Optional[str] = None
    
class ComplianceReport(BaseModel):
    paper_title: str
    findings: list[ComplianceFinding] = Field(
        description="Individual, atomic compliance findings"
    )
    action_items: list[str] = Field(
        description="Administrative or follow-up actions"
    )
    
class SubmissionRequirement(BaseModel):
    requirement_number: int
    category: str
    stage: Literal[
        "MANUSCRIPT_SUBMISSION",
        "POST_ACCEPTANCE",
        "PRESENTATION",
        "REGISTRATION",
        "CONFERENCE_ATTENDANCE",
        "OTHER"
    ]
    requirement: str
    guideline_evidence: str
    verification_method: str
    
class GuidelineRequirements(BaseModel):
    requirements: list[SubmissionRequirement]

# Load environment variables
load_dotenv()

# Initialize the LLM
llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite"
    # temperature=0
)

# Register our tools
tools = [analyze_paper_pdf]

guideline_extractor = create_agent(
    model=llm,
    tools=[get_submission_requirements],
    response_format=GuidelineRequirements,
    system_prompt="""
    You are a conference submission guideline extraction agent.

    Your task is to identify every distinct requirement stated
    in the conference submission guidelines.

    Rules:
    1. Extract requirements only from the retrieved guidelines.
    2. Do not evaluate a research paper at this stage.
    3. Keep independent requirements separate.
    4. Include formatting, page limits, figures, tables, authors, affiliations, citations, references, language, originality, registration, and presentation requirements when specified.
    5. Do not invent requirements that are not stated in the guidelines.
    6. Preserve the relevant guideline wording as evidence.
    7. Assign sequential requirement numbers starting from 1.
    8. Describe how each requirement can be verified. If manual inspection or an external tool is needed, state that.
    9. Split compound requirements into independent requirements. For example, author address, affiliation, email, and corresponding author designation should be separate when independently verifiable.
    10. Assign the appropriate stage field to each requirement: MANUSCRIPT_SUBMISSION, POST_ACCEPTANCE, PRESENTATION, REGISTRATION, CONFERENCE_ATTENDANCE, or OTHER.
    11. Preserve all distinct requirements, but do not duplicate the same requirement merely because it appears in multiple places.
    12. Extract deadlines, file naming rules, presentation requirements, and administrative requirements when they are explicitly stated.
    """
)

# Create the agent
agent = create_agent(
    model=llm,
    tools=tools,
    response_format=ComplianceReport,
    system_prompt="""
    You are Submission Sentinel, a research paper submission compliance assistant.

    Your responsibilities:
    1. Inspect research papers using the PDF analysis tool.
    2. Use the structured conference requirements supplied in the user message.
    3. Compare the paper against those supplied requirements.
    4. Generate a structured compliance report with evidence.

    Follow these rules strictly:

    - Use only requirements explicitly found in the retrieved submission guidelines.
    - Support every finding with evidence from the paper or guidelines whenever possible.
    - Mark each requirement as one of: COMPLIANT, NON-COMPLIANT, PARTIALLY COMPLIANT, or UNVERIFIABLE.
    - If the evidence shows that a requirement is satisfied, do not label it NON-COMPLIANT.
    - Ensure the status, evidence, and recommendation for each finding are logically consistent.
    - Do not claim to have visually inspected the PDF.
    - Do not claim to verify font sizes, margins, DPI, image quality, or layout using text extraction alone.
    - Do not infer that an official template was used merely because the document resembles IEEE formatting.
    - If a check requires a capability you do not have, mark it UNVERIFIABLE and explain why.
    - Distinguish verified facts, reasonable inferences, and unverified claims.

    - Every compliance finding must include:
    1. The exact requirement or a faithful summary.
    2. Evidence from the guidelines.
    3. Evidence from the paper, when applicable.
    4. The compliance status.
    5. A recommendation, if needed.

    - Do not mark a requirement COMPLIANT merely because no violation was found.
    
    EVIDENCE QUALITY RULES:

    - Mark a requirement COMPLIANT only when the available evidence directly supports every condition in that requirement.
    - Do not treat the absence of a detected problem as proof of compliance.
    - For tables, text extraction may reveal table content, but it cannot prove that a table is not an image. Mark table format UNVERIFIABLE unless reliable evidence establishes its format.
    - For sequential numbering, verify the actual extracted sequence before marking numbering COMPLIANT. Do not assume numbering is correct merely because some numbered items are present.
    - For citation checks, look for explicit in-text references to the relevant figures, tables, or bibliography entries. Numbering alone is insufficient.
    - For full-address requirements, do not assume that an institution name, department, city, and country automatically constitute a full postal address.
    - When only some conditions are supported by evidence, mark the requirement PARTIALLY COMPLIANT if appropriate; otherwise use UNVERIFIABLE when compliance cannot be established.
    
    - Mark a requirement UNVERIFIABLE when the available tools cannot establish compliance.
    - Text extraction alone cannot establish: grammatical correctness, originality, plagiarism, visual formatting, image resolution, table image format, or page-boundary containment.
    - Sequential numbering alone does not prove that all references, figures, and tables are correctly cited.
    - Extracted table text or rows and columns alone do not prove that tables are not pictorial. Mark table format UNVERIFIABLE unless reliable evidence establishes that the tables are not images.
    - Do not mark all references, figures, and tables as COMPLIANT based on a few examples. Verify each required item against the extracted in-text citations. If exhaustive verification is not possible, mark the requirement UNVERIFIABLE and explain the limitation.
    - Do not claim that a plagiarism check was performed unless an actual plagiarism detection tool was used.
    - When evidence is incomplete, explain the limitation instead of guessing.   
    - Do not infer a prohibited author position from an email address, student ID, or institutional email format alone.
    - Evaluate author titles, positions, affiliations, and corresponding-author designation as separate checks.
    - Do not mark a requirement COMPLIANT merely because it is acknowledged or because no violation was detected.
    - Distinguish manuscript compliance from author-side actions that must happen after acceptance.
    - Use the structured, atomic requirements supplied in the user message. Do not independently re-extract or redefine the requirements.
    - Split compound requirements into separate checks. For example, a requirement covering figure resolution, table format, text readability, and page boundaries must produce four independent checks.
    - Evaluate each atomic requirement against the paper evidence independently.
    - Assign exactly one status to each atomic requirement: COMPLIANT, NON-COMPLIANT, PARTIALLY COMPLIANT, or UNVERIFIABLE.
    - If an atomic requirement contains multiple conditions that cannot reasonably be separated, evaluate every condition and assign the overall status based on the evidence for all conditions.
    - Do not combine independent requirements into a single finding merely because they appear in the same sentence in the conference guidelines.
    - Track administrative obligations separately from manuscript compliance requirements.
    - When a requirement is only partially checked, explicitly state which part was verified and which part remains unverified.
    - Never mark a multi-condition requirement COMPLIANT if any explicitly required condition is missing or unverified.
    - If a requirement asks for multiple items, assess each item independently before assigning an overall status.
    - If the paper provides author emails but does not designate a corresponding author, do not mark the entire corresponding-author requirement COMPLIANT.
    - Separate sequential numbering from citation verification. Correct numbering does not prove that every figure, table, and reference is cited in the text.
    - Separate manuscript requirements from administrative obligations such as registration and presentation. Report administrative obligations as action items unless completion can be independently verified.
    - Give every atomic requirement a unique finding number.
    - Include every detailed finding in the executive summary status counts, except administrative action items that are tracked separately.
    - Calculate summary counts from the final detailed findings. Do not estimate or invent the counts.
    - Use the same status for a requirement in the executive summary and detailed findings.
    - If a requirement is split into multiple atomic checks, count each check separately in the summary.
    - Be precise, neutral, and evidence-based.
    - Return the report using the required structured output schema.
    - Create one finding for each independent compliance requirement. Do not combine separate checks into one finding.
    - Use only the four permitted compliance statuses. Do not include administrative obligations as compliance findings; place them in action_items instead.
    - Assign sequential finding numbers starting from 1. Ensure each finding contains evidence from the guidelines and paper, when available. Explain limitations when evidence is insufficient.
    - Do not generate executive summary counts. Python will calculate them from the structured findings.
    - Before evaluating the corresponding-author requirement, inspect the extracted paper content for an explicit corresponding-author designation.
    - If the extracted content explicitly identifies a corresponding author and provides that person's email address, mark the corresponding-author requirement COMPLIANT and cite the relevant text as evidence.
    - If author emails are present but no corresponding author is explicitly identified, mark the requirement NON-COMPLIANT.
    - If the extracted text is incomplete or ambiguous, mark the requirement UNVERIFIABLE rather than guessing.
    
    COMPLETENESS REQUIREMENTS:

    1. Use the structured requirements supplied in the user message.
    2. Evaluate every applicable manuscript requirement separately.
    3. Do not arbitrarily limit the number of findings. The number of findings must reflect the requirements actually identified in the guidelines.
    4. Use the PDF analysis tool's extracted page count to evaluate the page limit whenever the guidelines specify a numeric limit.
    5. Use available paper text and section headings as evidence. Do not mark a requirement UNVERIFIABLE if the available extracted evidence is sufficient to evaluate it.
    6. Mark visual-only requirements, such as exact margins, font sizes, figure DPI, and visual layout, UNVERIFIABLE when text extraction cannot establish compliance.
    7. Evaluate each applicable manuscript requirement from the supplied requirements, including author details, affiliations, figures, tables, citations, references, language quality, and originality when specified. If a check cannot be established from the available evidence or tools, mark it UNVERIFIABLE. Track administrative obligations separately in action_items.
    8. Before returning the report, check that every applicable manuscript requirement has a corresponding finding linked to its original requirement_number. Assign sequential finding numbers starting from 1.
    
    ACTION ITEM CONSISTENCY:

    1. Include every required corrective action from findings marked NON-COMPLIANT or PARTIALLY COMPLIANT in action_items.
    2. Include important manual verification tasks from UNVERIFIABLE findings when those checks are necessary before submission.
    3. Keep administrative actions, such as registration and presentation, separate from manuscript corrections where possible.
    4. Do not omit a recommendation from the action checklist merely because it was already mentioned in a finding.
    5. Avoid duplicate action items. Combine only tasks that genuinely refer to the same corrective action.
    
    EVALUATION WORKFLOW:

    1. Use the structured conference requirements supplied in the user message as the source of submission rules.
    2. Do not retrieve the conference guidelines again.
    3. Evaluate every applicable manuscript requirement separately.
    4. Do not evaluate presentation or conference attendance requirements against the research paper PDF.
    5. Use the PDF analysis tool to gather evidence before assigning statuses.
    6. Mark requirements UNVERIFIABLE when available evidence is insufficient.
    7. Include corrective recommendations for NON-COMPLIANT findings.
    8. Do not invent requirements or claim that visual checks were performed.
    """
)


def main():
    print("Submission Sentinel is ready!\n")

    pdf_path = input(
        "Enter the full path to your research paper PDF: "
    ).strip().strip('"')

    submission_url = input(
        "Enter the conference submission guidelines URL: "
    ).strip()

    # --------------------------------------------------
    # STAGE 1: Extract conference requirements
    # --------------------------------------------------

    print("\nStage 1: Extracting conference requirements...")

    guideline_response = guideline_extractor.invoke({
        "messages": [
            {
                "role": "user",
                "content": (
                    "Retrieve and extract all submission requirements "
                    f"from this conference guidelines page: {submission_url}"
                )
            }
        ]
    })

    requirements_report = guideline_response["structured_response"]

    print(
        f"Extracted {len(requirements_report.requirements)} requirements."
    )

    # Convert the Pydantic model into JSON for Stage 2
    requirements_json = json.dumps(
        requirements_report.model_dump(),
        indent=2
    )

    # --------------------------------------------------
    # STAGE 2: Evaluate the research paper
    # --------------------------------------------------

    print("\nStage 2: Evaluating the research paper...")

    # Extract the paper directly before asking the AI to evaluate it.
    paper_content = analyze_paper_pdf.invoke({
        "pdf_path": pdf_path
    })

    evaluation_prompt = f"""
    Evaluate the research paper against the conference requirements below.

    IMPORTANT REQUIREMENT COVERAGE RULES:
    1. For every finding, populate requirement_number using the exact
    requirement_number from the extracted conference requirements.
    2. Evaluate each applicable manuscript requirement separately.
    3. Do not merge different requirements into one finding.
    4. If one requirement needs multiple findings, reuse its
    requirement_number.
    5. Do not evaluate presentation, registration, or attendance
    requirements against the PDF.
    6. Do not invent requirements.

    Extracted paper content:
    {paper_content}

    Conference guidelines URL:
    {submission_url}

    Extracted conference requirements:
    {requirements_json}

    Evaluate only requirements applicable to the manuscript itself.
    Do not evaluate presentation, registration, or attendance requirements
    against the PDF.

    PAPER TITLE RULES:
    - Read the paper title from the extracted text of the PDF's first page.
    - Use the actual title printed in the manuscript.
    - Do not use the PDF filename as the paper title.
    - Do not invent, shorten, or replace the title with a generic title.
    - Preserve the title's original wording and punctuation.
    - If the title cannot be identified confidently, use "Unable to determine".

    Use the extracted paper content provided above to evaluate
    the manuscript against the supplied conference requirements.

    Do not assume the PDF extraction failed if the extracted content
    is present in the prompt.

    Identify the paper title from the first page's extracted text.
    Do not use the PDF filename as the title.

    Return a structured ComplianceReport using the required schema.
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

    # STAGE 3: REQUIREMENT COVERAGE CHECK

    print("\n" + "=" * 60)
    print("REQUIREMENT COVERAGE CHECK")
    print("=" * 60)

    # Only check requirements intended for manuscript submission.
    manuscript_requirements = [
        req
        for req in requirements_report.requirements
        if req.stage == "MANUSCRIPT_SUBMISSION"
    ]

    # Collect the original requirement numbers referenced by findings.
    manuscript_requirement_numbers = {
        req.requirement_number
        for req in manuscript_requirements
    }

    evaluated_requirement_numbers = {
        finding.requirement_number
        for finding in report.findings
        if finding.requirement_number is not None
        and finding.requirement_number in manuscript_requirement_numbers
    }

    # Find manuscript requirements without a matching finding.
    missing_requirements = [
        req
        for req in manuscript_requirements
        if req.requirement_number not in evaluated_requirement_numbers
    ]

    print(f"Manuscript requirements extracted: {len(manuscript_requirements)}")
    print(
        "Distinct manuscript requirements with findings: "
        f"{len(evaluated_requirement_numbers)}"
    )
    print(f"Potentially missing requirements: {len(missing_requirements)}")

    if missing_requirements:
        print("\nRequirements that may have been skipped:")

        for req in missing_requirements:
            print(
                f"\nRequirement {req.requirement_number}: "
                f"{req.requirement}"
            )
            print(f"Category: {req.category}")
            print(f"Stage: {req.stage}")
    else:
        print("\nAll extracted manuscript-submission requirements")
        print("have at least one matching compliance finding.")

    # Detect findings that do not reference an extracted requirement.
    unlinked_findings = [
        finding
        for finding in report.findings
        if finding.requirement_number is None
    ]

    if unlinked_findings:
        print(
            f"\nWarning: {len(unlinked_findings)} finding(s) "
            "have no requirement number."
        )
        print("Their coverage cannot be verified automatically.")
        
    # Detect findings linked to nonexistent requirement numbers.
    all_requirement_numbers = {
        req.requirement_number
        for req in requirements_report.requirements
    }

    invalid_requirement_findings = [
        finding
        for finding in report.findings
        if finding.requirement_number is not None
        and finding.requirement_number not in all_requirement_numbers
    ]

    if invalid_requirement_findings:
        print(
            f"\nWarning: {len(invalid_requirement_findings)} finding(s) "
            "reference nonexistent requirement numbers."
        )

        for finding in invalid_requirement_findings:
            print(
                f"Finding {finding.finding_number} references "
                f"Requirement {finding.requirement_number}."
            )

    # --------------------------------------------------
    # STAGE 4: Calculate status counts
    # --------------------------------------------------

    status_counts = {
        "COMPLIANT": 0,
        "NON-COMPLIANT": 0,
        "PARTIALLY COMPLIANT": 0,
        "UNVERIFIABLE": 0,
    }

    for finding in report.findings:
        status_counts[finding.status] += 1

    # --------------------------------------------------
    # STAGE 5: DISPLAY FINAL REPORT
    # --------------------------------------------------

    print("\n" + "=" * 60)
    print("SUBMISSION SENTINEL REPORT")
    print("=" * 60)

    print(f"\nPaper Title: {report.paper_title}")

    print("\n1. EXECUTIVE SUMMARY")
    print("-" * 40)

    for status, count in status_counts.items():
        print(f"{status}: {count}")

    print(f"Total Findings: {len(report.findings)}")

    print("\n2. DETAILED COMPLIANCE FINDINGS")
    print("-" * 40)

    for finding in report.findings:
        print(
            f"\nFinding {finding.finding_number} "
            f"(Requirement {finding.requirement_number}): "
            f"{finding.requirement}"
        )
        print(f"Category: {finding.category}")
        print(f"Guidelines Evidence: {finding.guidelines_evidence}")
        print(f"Paper Evidence: {finding.paper_evidence}")
        print(f"Status: {finding.status}")

        if finding.recommendation:
            print(f"Recommendation: {finding.recommendation}")

    print("\n3. ACTION ITEMS CHECKLIST")
    print("-" * 40)

    if report.action_items:
        for item in report.action_items:
            print(f"[ ] {item}")
    else:
        print("No separate action items reported.")
        
if __name__ == "__main__":
    main()