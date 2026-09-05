"""
backend/app/scripts/rag_phase2_smoke.py

Development-only smoke test for the RAG Phase 2 pipeline.

Usage (from the backend/ directory):
    uv run python -m app.scripts.rag_phase2_smoke uploads/your-document.pdf

Prints page count, word count, chunk count, and a preview of the first 3 chunks.
DO NOT commit files that print private document text. Keep this script dev-only.
"""
import sys

from app.services.rag.document_processor import (
    NoExtractableTextError,
    process_pdf_from_storage,
)
from app.services.rag.pdf_extractor import PdfExtractionError


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: uv run python -m app.scripts.rag_phase2_smoke <s3_key>")
        print("Example: uv run python -m app.scripts.rag_phase2_smoke uploads/abc123_example.pdf")
        sys.exit(1)

    s3_key = sys.argv[1]
    print(f"Processing S3 key: {s3_key}\n")

    try:
        result = process_pdf_from_storage(s3_key)
    except FileNotFoundError:
        print(f"ERROR: Object '{s3_key}' does not exist in storage.")
        sys.exit(2)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(3)
    except NoExtractableTextError:
        print("ERROR: PDF has no extractable text layer (scanned/image-only).")
        sys.exit(4)
    except PdfExtractionError as exc:
        print(f"ERROR: PDF parsing failed – {exc}")
        sys.exit(5)

    print(f"pages              = {result.page_count}")
    print(f"extracted words    = {result.extracted_word_count}")
    print(f"chunks             = {len(result.chunks)}")
    print()

    for chunk in result.chunks[:3]:
        print("-" * 80)
        print(f"chunk={chunk.chunk_index}  pages={chunk.page_start}-{chunk.page_end}")
        print(f"words={chunk.word_start}-{chunk.word_end}  count={chunk.word_count}")
        print(f"checksum={chunk.text_checksum[:16]}...")
        print()
        print(chunk.clean_text[:500])
        print()

    if len(result.chunks) > 3:
        print(f"... ({len(result.chunks) - 3} more chunks)")


if __name__ == "__main__":
    main()
