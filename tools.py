import re
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from langchain.tools import tool
from langchain_text_splitters import RecursiveCharacterTextSplitter


@tool
def get_submission_requirements(url: str) -> str:
    """Fetch a conference submission webpage and extract its readable text.
    Use this tool to find paper limits, formatting rules, required sections,
    submission instructions, and deadlines."""
    try:
        response = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "SubmissionSentinel/1.0"}
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        text = soup.get_text(separator=" ", strip=True)

        if not text:
            return "No readable text found on this webpage."

        return text[:15000]

    except requests.RequestException as e:
        return f"Could not retrieve the webpage: {e}"




@tool
def analyze_paper_pdf(pdf_path: str) -> str:
    """Extract text from a research paper PDF and organize it
    into sections using common academic headings."""

    try:
        reader = PdfReader(pdf_path)

        if reader.is_encrypted:
            return "The PDF is encrypted and cannot be inspected."

        # Step 1: Extract text while preserving page markers.
        page_count = len(reader.pages)
        page_text = []

        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            page_text.append(
                f"\n--- Page {page_number} ---\n{text}"
            )

        full_text = "\n".join(page_text)

        if not full_text.strip():
            return "No extractable text was found in the PDF."

        # Step 2: Define common research-paper headings.
        heading_patterns = {
            "Abstract": r"abstract",
            "Keywords": r"keywords?",
            "Introduction": r"introduction",
            "Literature Review": r"literature review|related work",
            "Methodology": r"methodology|methods|materials and methods",
            "Proposed System": r"proposed system|proposed method|proposed approach",
            "System Architecture": r"system architecture|architecture",
            "Results and Discussion": r"results and discussion|results|discussion",
            "Conclusion": r"conclusion|conclusions",
            "Future Work": r"future work|future scope",
            "Acknowledgments": r"acknowledg(e)?ments?",
            "References": r"references|bibliography",
        }

        # Step 3: Recognize headings appearing on their own lines.
        
        def detect_heading(line):
            cleaned = line.strip()

            if not cleaned or len(cleaned) > 120:
                return None

            # Remove page markers.
            if re.fullmatch(r"--- Page \d+ ---", cleaned):
                return None

            # Remove numbering such as:
            # 1. Introduction, II. Related Work, IV. IMPLEMENTATION DETAILS
            cleaned = re.sub(
                r"^\s*(?:(?:\d+(?:\.\d+)*|[IVXLCDM]+)[.)]?\s+)",
                "",
                cleaned,
                flags=re.IGNORECASE,
            ).strip()

            heading_patterns = {
                "Abstract": r"abstract",
                "Keywords": r"keywords?",
                "Introduction": r"introduction",
                "Literature Review": r"literature review|related work",
                "Methodology": r"proposed methodology|methodology|methods|materials and methods",
                "Proposed System": r"proposed system|proposed method|proposed approach",
                "System Architecture": r"system architecture|architecture",
                "Implementation Details": r"implementation details|implementation",
                "Results and Discussion": r"experimental results and analysis|results and discussion|results|discussion",
                "Conclusion": r"conclusion and future work|conclusions?|summary of contributions",
                "Future Work": r"future work|future scope",
                "Acknowledgments": r"acknowledg(e)?ments?",
                "References": r"references|bibliography",
            }

            for section_name, pattern in heading_patterns.items():
                # Match either a standalone heading or a heading followed
                # by a separator, as in "Abstract— Counterfeit medicines..."
                if re.match(
                    rf"^\s*(?:{pattern})(?:\s*[:—–-]\s*|\s*$)",
                    cleaned,
                    flags=re.IGNORECASE,
                ):
                    return section_name

            return None

        # Step 4: Group text under detected headings.
        sections = {}
        current_section = "Unclassified / Front Matter"
        sections[current_section] = []

        
        for line in full_text.splitlines():
            detected_heading = detect_heading(line)

            if detected_heading:
                current_section = detected_heading
                sections.setdefault(current_section, [])

                # Preserve text appearing after an inline heading,
                # such as "Abstract— Counterfeit medicines..."
                match = re.match(
                    r"^\s*(?:abstract|keywords?)\s*[—–:-]\s*(.+)$",
                    line.strip(),
                    flags=re.IGNORECASE,
                )

                if match:
                    sections[current_section].append(match.group(1))

            else:
                sections[current_section].append(line)
                

        # Step 5: Split each section into smaller chunks.
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=150,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        output = [
            f"PDF page count: {page_count}",
            f"Total extracted characters: {len(full_text)}",
            "\nSECTION-WISE PAPER CONTENT",
            "=" * 40,
        ]

        total_chunks = 0
        chunk_number = 1

        for section_name, lines in sections.items():
            section_text = "\n".join(lines).strip()

            if not section_text:
                continue

            chunks = text_splitter.split_text(section_text)
            total_chunks += len(chunks)

            output.append(f"\n## {section_name}")
            output.append("-" * 30)

            for chunk in chunks:
                output.append(
                    f"\n[Chunk {chunk_number} | Section: {section_name}]\n"
                    f"{chunk}"
                )
                chunk_number += 1

        output.insert(3, f"Total chunks created: {total_chunks}")
        return "\n".join(output)

    except Exception as e:
        return f"Could not analyze the PDF: {e}"