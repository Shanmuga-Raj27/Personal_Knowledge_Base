"""
backend/tests/AI-test/evaluate_search.py

Automated script to evaluate metadata-based AI search accuracy.
Seeds controlled metadata records, runs golden queries, and measures precision.
"""
import os
import sys
import json
import asyncio

# Add backend directory to sys.path for clean app imports
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_path = os.path.abspath(os.path.join(current_dir, "..", ".."))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

# Load environment variables
from dotenv import load_dotenv
env_path = os.path.join(backend_path, "..", "others", ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

from app.database.database import SessionLocal
from app.database.db_models import User, FileMetadata
from app.services.AI.vector_service import upsert_file_vector, delete_file_vector, search_file_vectors


async def run_evaluation():
    print("--------------------------------------------------")
    print("Starting AI Search Accuracy Evaluation Pipeline")
    print("--------------------------------------------------")

    # Step 0: Ensure golden_dataset.json exists in tests/AI-test folder
    dataset_path = os.path.join(current_dir, "golden_dataset.json")
    if not os.path.exists(dataset_path):
        print("golden_dataset.json not found. Auto-generating dataset...")
        from generate_dataset import generate
        generate()

    db = SessionLocal()
    seeded_files = []
    test_user = None

    try:
        # Step 1: Create or fetch test user
        test_email = "search_eval_user@example.com"
        test_user = db.query(User).filter(User.email == test_email).first()
        if not test_user:
            print("Creating temporary test user...")
            test_user = User(
                email=test_email,
                hashed_password="dummy_password_hash",
                status="active"
            )
            db.add(test_user)
            db.commit()
            db.refresh(test_user)

        # Step 2: Load Golden Dataset
        with open(dataset_path, "r", encoding="utf-8") as f:
            dataset = json.load(f)

        mock_files_data = dataset["mock_files"]
        test_queries = dataset["test_queries"]

        # Step 3: Insert and Index Mock Files
        print(f"\nSeeding {len(mock_files_data)} mock metadata files...")
        for file_data in mock_files_data:
            # Check if record already exists to avoid duplicates
            db_file = db.query(FileMetadata).filter(
                FileMetadata.filename == file_data["filename"],
                FileMetadata.userid == test_user.id
            ).first()

            if not db_file:
                db_file = FileMetadata(
                    s3_key=f"uploads/eval_test_{file_data['filename']}",
                    filename=file_data["filename"],
                    content_type="application/octet-stream",
                    size_bytes=1024,
                    status="active",
                    title=file_data["title"],
                    description=file_data["description"],
                    tags=file_data["tags"],
                    userid=test_user.id,
                    indexing_status="INDEXING"
                )
                db.add(db_file)
                db.commit()
                db.refresh(db_file)

            seeded_files.append(db_file)

            # Generate vector embedding and upsert to Qdrant with retry backoff
            indexed = False
            retries = 3
            backoff = 1.5
            for attempt in range(retries):
                indexed = await upsert_file_vector(
                    file_id=db_file.fileid,
                    user_id=test_user.id,
                    filename=db_file.filename,
                    title=db_file.title,
                    description=db_file.description,
                    tags=db_file.tags
                )
                if indexed:
                    break
                await asyncio.sleep(backoff * (attempt + 1))

            if indexed:
                db_file.is_indexed = True
                db_file.indexing_status = "INDEXED"
            else:
                db_file.indexing_status = "FAILED"
                print(f"  Warning: Failed to index {db_file.filename}")
            db.commit()

            # Rate limit backoff delay for embedding generation
            await asyncio.sleep(0.4)

        # Step 4: Map file ids to filenames for verification
        file_map = {f.fileid: f.filename for f in seeded_files}

        # Step 5: Execute Test Queries & Measure Accuracy
        print(f"\nRunning {len(test_queries)} evaluation test queries...")
        print("--------------------------------------------------")
        
        correct_rank1 = 0
        correct_top3 = 0
        total_queries = len(test_queries)

        for i, q_item in enumerate(test_queries, 1):
            query = q_item["query"]
            expected = q_item["expected_filename"]

            # Run similarity search through vector service
            results = await search_file_vectors(query_text=query, user_id=test_user.id, limit=3)
            matched_filenames = [file_map[fid] for fid, _ in results if fid in file_map]

            is_correct_rank1 = len(matched_filenames) > 0 and matched_filenames[0] == expected
            is_correct_top3 = expected in matched_filenames

            if is_correct_rank1:
                correct_rank1 += 1
                correct_top3 += 1
                status_icon = "[PASS]"
                status_text = "Rank 1 Match"
            elif is_correct_top3:
                correct_top3 += 1
                status_icon = "[PARTIAL]"
                status_text = "Top 3 Match"
            else:
                status_icon = "[FAIL]"
                status_text = "No Match"

            print(f"Query {i}: \"{query}\"")
            print(f" -> Expected: {expected}")
            print(f" -> Found:    {matched_filenames if matched_filenames else '[]'}")
            print(f" -> Result:   {status_icon} {status_text}\n")

        # Step 6: Print Evaluation Report
        accuracy_rank1 = (correct_rank1 / total_queries) * 100
        accuracy_top3 = (correct_top3 / total_queries) * 100

        print("--------------------------------------------------")
        print("AI Search Evaluation Metrics Summary")
        print("--------------------------------------------------")
        print(f"Total Queries Run:      {total_queries}")
        print(f"Exact Matches (Rank 1):  {correct_rank1} / {total_queries} ({accuracy_rank1:.1f}%)")
        print(f"Top 3 Matches:           {correct_top3} / {total_queries} ({accuracy_top3:.1f}%)")
        print("--------------------------------------------------")

    except Exception as exc:
        print(f"\nError during evaluation run: {str(exc)}")
    finally:
        # Cleanup seeded mock files & user safely
        print("\nCleaning up evaluation records from databases...")
        try:
            for db_file in seeded_files:
                try:
                    await delete_file_vector(db_file.fileid)
                except Exception:
                    pass
                try:
                    db.delete(db_file)
                except Exception:
                    pass
            if test_user:
                try:
                    db.delete(test_user)
                except Exception:
                    pass
            db.commit()
            print("Cleanup completed successfully.")
        except Exception as cleanup_exc:
            print(f"Error during cleanup: {str(cleanup_exc)}")
        finally:
            db.close()


if __name__ == "__main__":
    asyncio.run(run_evaluation())
