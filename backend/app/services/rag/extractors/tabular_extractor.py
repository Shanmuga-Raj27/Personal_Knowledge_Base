"""
backend/app/services/rag/extractors/tabular_extractor.py

Phase 2 Extractor: Tabular files (CSV, TSV, and Excel .xlsx).
Zero external dependencies (pure Python standard library: csv, zipfile, xml.etree.ElementTree).
"""
import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET

from app.services.rag.schemas import ExtractedPage


def extract_csv_pages(raw_bytes: bytes, filename: str = "") -> list[ExtractedPage]:
    """Extract CSV or TSV tabular data into header-prefixed semantic rows.

    Batches every 50 rows into a virtual page so downstream chunking and
    embeddings maintain strong semantic context per record.
    """
    # Detect encoding
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw_bytes.decode("utf-8", errors="replace")

    text = text.strip()
    if not text:
        return []

    # Determine delimiter: tab for .tsv or inspect first line
    delimiter = "\t" if (filename or "").lower().endswith(".tsv") else ","
    sample_line = text.split("\n", 1)[0]
    if delimiter != "\t" and "\t" in sample_line and "," not in sample_line:
        delimiter = "\t"
    elif delimiter != "\t" and ";" in sample_line and "," not in sample_line:
        delimiter = ";"

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    all_rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not all_rows:
        return []

    headers = [h.strip() or f"Column_{i+1}" for i, h in enumerate(all_rows[0])]
    data_rows = all_rows[1:]
    if not data_rows:
        # Only headers present
        header_text = "Table Columns: " + ", ".join(headers)
        return [ExtractedPage(page_number=1, text=header_text)]

    pages: list[ExtractedPage] = []
    rows_per_page = 50

    for page_idx, start_idx in enumerate(range(0, len(data_rows), rows_per_page), start=1):
        batch = data_rows[start_idx : start_idx + rows_per_page]
        lines = []
        for row_num, row in enumerate(batch, start=start_idx + 1):
            row_items = []
            for col_idx, cell_value in enumerate(row):
                val = cell_value.strip()
                if val:
                    col_name = headers[col_idx] if col_idx < len(headers) else f"Column_{col_idx+1}"
                    row_items.append(f"[{col_name}]: {val}")
            if row_items:
                lines.append(f"Row {row_num}: " + " | ".join(row_items))

        if lines:
            pages.append(ExtractedPage(page_number=page_idx, text="\n".join(lines)))

    return pages


def extract_excel_pages(raw_bytes: bytes, filename: str = "") -> list[ExtractedPage]:
    """Extract Excel .xlsx sheets into page-mapped semantic records.

    Zero external dependencies: reads the zipped OpenXML structure using
    zipfile and xml.etree.ElementTree directly.
    """
    if not zipfile.is_zipfile(io.BytesIO(raw_bytes)):
        raise ValueError(
            "Legacy Excel (.xls binary) is not supported. Please save as modern .xlsx or .csv."
        )

    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
        names = z.namelist()

        # 1. Parse shared strings if present
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in names:
            tree = ET.fromstring(z.read("xl/sharedStrings.xml"))
            ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            si_nodes = tree.findall(".//m:si", ns) or tree.findall(".//si")
            for si in si_nodes:
                t_nodes = si.findall(".//m:t", ns) or si.findall(".//t")
                shared_strings.append("".join(t.text or "" for t in t_nodes))

        # 2. Parse workbook.xml to extract sheet names
        sheet_names: list[str] = []
        if "xl/workbook.xml" in names:
            wb_tree = ET.fromstring(z.read("xl/workbook.xml"))
            ns_wb = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            sheet_nodes = wb_tree.findall(".//m:sheet", ns_wb) or wb_tree.findall(".//sheet")
            for sheet in sheet_nodes:
                name = sheet.attrib.get("name", "")
                if name:
                    sheet_names.append(name)

        # 3. Locate all worksheet files
        sheet_files = [f for f in names if f.startswith("xl/worksheets/sheet") and f.endswith(".xml")]
        # Sort naturally: sheet1.xml, sheet2.xml ...
        sheet_files.sort(key=lambda s: [int(c) for c in re.findall(r"\d+", s)] or [0])

        pages: list[ExtractedPage] = []
        for idx, sheet_file in enumerate(sheet_files, start=1):
            sheet_title = sheet_names[idx - 1] if idx - 1 < len(sheet_names) else f"Sheet {idx}"
            sheet_tree = ET.fromstring(z.read(sheet_file))
            ns_s = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

            rows_data: list[list[str]] = []
            row_nodes = sheet_tree.findall(".//m:row", ns_s) or sheet_tree.findall(".//row")
            for row_elem in row_nodes:
                row_cells: list[str] = []
                c_nodes = row_elem.findall(".//m:c", ns_s) or row_elem.findall(".//c")
                for c in c_nodes:
                    cell_type = c.get("t", "")
                    v_node = c.find("m:v", ns_s) or c.find("v")
                    raw_val = v_node.text.strip() if v_node is not None and v_node.text else ""

                    if cell_type == "s" and raw_val.isdigit():
                        s_idx = int(raw_val)
                        val = shared_strings[s_idx] if s_idx < len(shared_strings) else raw_val
                    elif cell_type == "inlineStr":
                        is_t = c.find(".//m:t", ns_s) or c.find(".//t")
                        val = is_t.text.strip() if is_t is not None and is_t.text else raw_val
                    else:
                        val = raw_val

                    row_cells.append(val)

                if any(cell.strip() for cell in row_cells):
                    rows_data.append(row_cells)

            if not rows_data:
                continue

            headers = [h.strip() or f"Column_{c_idx+1}" for c_idx, h in enumerate(rows_data[0])]
            sheet_lines = [f"Sheet Name: {sheet_title}"]

            for r_idx, row in enumerate(rows_data[1:], start=2):
                row_parts = []
                for c_idx, val in enumerate(row):
                    clean_val = val.strip()
                    if clean_val:
                        h = headers[c_idx] if c_idx < len(headers) else f"Column_{c_idx+1}"
                        row_parts.append(f"[{h}]: {clean_val}")
                if row_parts:
                    sheet_lines.append(f"Row {r_idx}: " + " | ".join(row_parts))

            if len(sheet_lines) > 1:
                pages.append(ExtractedPage(page_number=len(pages) + 1, text="\n".join(sheet_lines)))

    return pages
