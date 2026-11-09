"""
backend/app/services/rag/extractors/docx_extractor.py

Phase 3 Extractor: Microsoft Word (.docx) documents.
Zero external dependencies (pure Python standard library: zipfile, xml.etree.ElementTree).
"""
import io
import zipfile
import xml.etree.ElementTree as ET

from app.services.rag.schemas import ExtractedPage


def extract_docx_pages(raw_bytes: bytes, filename: str = "") -> list[ExtractedPage]:
    """Extract paragraphs and embedded tables from Word (.docx) documents.

    - Preserves body paragraph order.
    - Converts Word tables into Markdown grid tables.
    - Honors page breaks (<w:br w:type="page"/>) as natural page boundaries.
    """
    # Guard against legacy binary .doc (starts with OLE signature \xd0\xcf\x11\xe0)
    if raw_bytes.startswith(b"\xd0\xcf\x11\xe0"):
        raise ValueError(
            "Legacy Word (.doc binary format) is not supported. Please save as modern .docx format."
        )

    if not zipfile.is_zipfile(io.BytesIO(raw_bytes)):
        raise ValueError(f"File '{filename}' is not a valid DOCX package.")

    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
        if "word/document.xml" not in z.namelist():
            raise ValueError(f"Invalid DOCX '{filename}': missing word/document.xml")

        xml_data = z.read("word/document.xml")
        tree = ET.fromstring(xml_data)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

        pages: list[ExtractedPage] = []
        current_page_lines: list[str] = []
        page_num = 1

        body = tree.find("w:body", ns) or tree.find(".//body") or tree

        for child in body:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

            if tag == "p":
                # Check for explicit page break in runs
                has_break = False
                for br in child.findall(".//w:br", ns) or child.findall(".//br"):
                    br_type = br.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}type") or br.attrib.get("type")
                    if br_type == "page":
                        has_break = True
                        break
                if not has_break:
                    last_breaks = child.findall(".//w:lastRenderedPageBreak", ns) or child.findall(".//lastRenderedPageBreak")
                    if last_breaks:
                        has_break = True

                # Extract text from all text nodes
                t_nodes = child.findall(".//w:t", ns) or child.findall(".//t")
                para_text = "".join(t.text or "" for t in t_nodes).strip()

                if has_break and current_page_lines:
                    pages.append(ExtractedPage(page_number=page_num, text="\n".join(current_page_lines)))
                    page_num += 1
                    current_page_lines = []

                if para_text:
                    current_page_lines.append(para_text)

            elif tag == "tbl":
                # Extract Word table into a Markdown table
                table_rows: list[list[str]] = []
                tr_nodes = child.findall(".//w:tr", ns) or child.findall(".//tr")
                for tr in tr_nodes:
                    row_cells: list[str] = []
                    tc_nodes = tr.findall(".//w:tc", ns) or tr.findall(".//tc")
                    for tc in tc_nodes:
                        tc_t_nodes = tc.findall(".//w:t", ns) or tc.findall(".//t")
                        cell_text = " ".join(t.text.strip() for t in tc_t_nodes if t.text and t.text.strip())
                        # Escape pipe characters for markdown compatibility
                        row_cells.append(cell_text.replace("\n", " ").replace("|", "/"))
                    if any(row_cells):
                        table_rows.append(row_cells)

                if table_rows:
                    md_lines: list[str] = []
                    headers = table_rows[0]
                    col_count = len(headers)
                    md_lines.append("| " + " | ".join(headers) + " |")
                    md_lines.append("| " + " | ".join(["---"] * col_count) + " |")

                    for row in table_rows[1:]:
                        padded = row + [""] * (col_count - len(row))
                        md_lines.append("| " + " | ".join(padded[:col_count]) + " |")

                    current_page_lines.append("\n".join(md_lines))

        if current_page_lines:
            pages.append(ExtractedPage(page_number=page_num, text="\n".join(current_page_lines)))

        # Fallback: if document had no page breaks and is long, split into ~600-word blocks
        if len(pages) == 1:
            words = pages[0].text.split()
            if len(words) > 800:
                pages = [
                    ExtractedPage(page_number=idx + 1, text=" ".join(words[i : i + 600]))
                    for idx, i in enumerate(range(0, len(words), 600))
                ]

        return pages
