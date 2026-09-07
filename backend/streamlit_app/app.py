"""
backend/streamlit_app/app.py

Development playground for the RAG Phase 6 API. A THIN client: it talks only
to the FastAPI backend over HTTP(S) and never connects to MySQL, Qdrant,
Redis, B2/S3, or Gemini directly.

Endpoints used:
    POST   /auth/login                     -> bearer token
    GET    /files                          -> list the user's files
    POST   /files/upload-url               -> presigned PUT URL (direct S3 upload)
    POST   /files/upload-complete          -> activate file + schedule indexing
    POST   /documents                      -> trigger/retry RAG indexing
    GET    /documents/{id}/index-status    -> indexing progress
    GET    /documents/{id}/chunks          -> chunk inspection
    POST   /rag/query                      -> SSE-streamed grounded answer

The bearer token lives only in st.session_state (never in source, never on disk).
"""
import json
import os

import pandas as pd
import requests
import streamlit as st

API_BASE = os.environ.get("RAG_API_BASE_URL", "http://localhost:8000")
PDF_CONTENT_TYPE = "application/pdf"

st.set_page_config(page_title="RAG Playground", layout="wide")


# ── Tiny API client helpers ──────────────────────────────────────────────

def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def api_error(resp: requests.Response) -> str:
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        detail = resp.text
    return f"HTTP {resp.status_code}: {detail}"


def login(email: str, password: str) -> str:
    resp = requests.post(
        f"{API_BASE}/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_active_files(token: str) -> list[dict]:
    resp = requests.get(
        f"{API_BASE}/files",
        params={"limit": 200},
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("items", [])


def get_presigned_put_url(token: str, filename: str, content_type: str) -> dict:
    resp = requests.post(
        f"{API_BASE}/files/upload-url",
        json={"filename": filename, "contentType": content_type},
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def upload_direct_to_s3(upload_url: str, data: bytes, content_type: str) -> None:
    resp = requests.put(
        upload_url,
        data=data,
        headers={"Content-Type": content_type},
        timeout=300,
    )
    resp.raise_for_status()


def complete_upload(token: str, key: str, filename: str) -> None:
    resp = requests.post(
        f"{API_BASE}/files/upload-complete",
        json={"key": key, "filename": filename},
        headers=auth_headers(token),
        timeout=60,
    )
    resp.raise_for_status()


def trigger_indexing(token: str, file_id: int | None = None, s3_key: str | None = None) -> dict:
    body = {}
    if file_id is not None:
        body["file_id"] = file_id
    else:
        body["s3_key"] = s3_key
    resp = requests.post(
        f"{API_BASE}/documents",
        json=body,
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_index_status(token: str, file_id: int) -> dict:
    resp = requests.get(
        f"{API_BASE}/documents/{file_id}/index-status",
        headers=auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_chunks(token: str, file_id: int, index_version: int | None = None) -> dict:
    params = {"index_version": index_version} if index_version is not None else {}
    resp = requests.get(
        f"{API_BASE}/documents/{file_id}/chunks",
        params=params,
        headers=auth_headers(token),
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


# ── Sidebar: connection + auth + query tuning ─────────────────────────────

st.sidebar.header("Connection")
api_base = st.sidebar.text_input("API base URL", value=API_BASE)
if api_base.strip():
    API_BASE = api_base.strip()

st.sidebar.subheader("Authentication")
with st.sidebar.expander("Log in (get a token)"):
    login_email = st.text_input("Email", key="login_email")
    login_password = st.text_input("Password", type="password", key="login_pass")
    if st.button("Get token"):
        try:
            token = login(login_email, login_password)
            st.session_state["token"] = token
            st.sidebar.success("Token stored (session only).")
        except Exception as exc:
            st.sidebar.error(f"Login failed: {exc}")

token = st.sidebar.text_input(
    "Bearer token",
    type="password",
    value=st.session_state.get("token", ""),
    help="Stored in session state only; never written to disk.",
)
if token:
    st.session_state["token"] = token

st.sidebar.subheader("Query tuning")
top_k = st.sidebar.slider("top_k (chunks)", min_value=1, max_value=20, value=6)
score_threshold = st.sidebar.slider("Similarity threshold", 0.0, 1.0, 0.35)

if not token:
    st.info("Log in from the sidebar, or paste a bearer token, to continue.")
    st.stop()

api_token: str = str(token)


# ── Shared: file picker source ────────────────────────────────────────────

def list_files() -> list[dict]:
    try:
        return get_active_files(api_token)
    except Exception as exc:
        st.error(f"Could not list files: {exc}")
        return []


def render_status(file_id: int) -> None:
    """Fetch + render index status for a file_id (used by both status buttons)."""
    try:
        status = get_index_status(api_token, file_id)
        st.progress(status["progress"])
        st.json(status)
    except Exception as exc:
        st.error(f"Status lookup failed: {exc}")


# ── Tab 1: Upload & Status ────────────────────────────────────────────────

tab_upload, tab_chunks, tab_query = st.tabs(
    ["Upload & Status", "Chunk Inspector", "Query Playground"]
)

with tab_upload:
    st.header("Upload a PDF (direct-to-S3 via presigned URL)")
    st.caption(
        "Bytes go straight to object storage; FastAPI only issues presigned URLs "
        "and verifies the upload. The RAG worker then indexes the PDF in the background."
    )

    uploaded = st.file_uploader("Choose a PDF", type=["pdf"])
    if uploaded is not None:
        data_bytes = uploaded.getvalue()
        if st.button("Upload & index", type="primary"):
            try:
                with st.spinner("Requesting presigned URL..."):
                    presigned = get_presigned_put_url(api_token, uploaded.name, PDF_CONTENT_TYPE)
                with st.spinner("Uploading to object storage..."):
                    upload_direct_to_s3(presigned["uploadUrl"], data_bytes, PDF_CONTENT_TYPE)
                with st.spinner("Confirming upload..."):
                    complete_upload(api_token, presigned["key"], uploaded.name)
                st.success(f"Uploaded. fileId={presigned['fileId']} key={presigned['key']}")
                st.session_state["watch_file_id"] = presigned["fileId"]
            except Exception as exc:
                st.error(f"Upload failed: {exc}")

    st.divider()
    st.subheader("Trigger / inspect a document")
    files = list_files()
    if files:
        options = {f"{f.get('fileId')} — {f.get('filename')} (status: {f.get('status')})": f for f in files}
        label = st.selectbox("Select your file", list(options.keys()))
        selected = options[label]
        col1, col2 = st.columns(2)
        if col1.button("Trigger RAG indexing"):
            try:
                result = trigger_indexing(api_token, file_id=selected["fileId"])
                st.session_state["watch_file_id"] = result["id"]
                st.success(f"Indexing started for fileId={result['id']} ({result['indexing_status']})")
            except Exception as exc:
                st.error(f"Trigger failed: {exc}")
        if col2.button("Watch status"):
            st.session_state["watch_file_id"] = selected["fileId"]
            render_status(int(selected["fileId"]))
    else:
        st.warning("No active files found for this account yet.")

    st.divider()
    watch_id = st.text_input(
        "or watch status by file_id", value=str(st.session_state.get("watch_file_id", ""))
    )
    if watch_id and st.button("Poll index status"):
        render_status(int(watch_id))


# ── Tab 2: Chunk Inspector ────────────────────────────────────────────────

with tab_chunks:
    st.header("Chunk Inspector")
    st.caption(
        "Shows the cleaned text the RAG engine actually hands to Gemini — "
        "proof of what was indexed before you query it."
    )
    files = list_files()
    if files:
        options = {f"{f.get('fileId')} — {f.get('filename')}": f for f in files}
        label = st.selectbox("Select your file", list(options.keys()), key="chunk_file")
        selected = options[label]
        file_id = selected["fileId"]
        show_version = st.text_input(
            "index_version (empty = active version)", value=""
        )
        if st.button("Load chunks", type="primary"):
            try:
                version = int(show_version) if show_version.strip() else None
                payload = get_chunks(api_token, file_id, version)
                st.write(
                    f"fileId={payload['file_id']}  index_version={payload['index_version']}  "
                    f"total chunks={payload['total']}"
                )
                for chunk in payload["chunks"]:
                    st.markdown(
                        f"**Chunk {chunk['chunk_index']}** — pages {chunk['page_start']}-"
                        f"{chunk['page_end']}, words {chunk['word_count']} "
                        f"(word {chunk['word_start']}-{chunk['word_end']})"
                    )
                    st.text_area(
                        "clean_text",
                        value=chunk["clean_text"],
                        height=140,
                        label_visibility="collapsed",
                        key=f"chunk_{payload['file_id']}_{payload['index_version']}_{chunk['chunk_index']}",
                    )
            except Exception as exc:
                st.error(f"Chunk load failed: {exc}")
    else:
        st.warning("No active files found for this account yet.")


# ── Tab 3: Query Playground ───────────────────────────────────────────────

with tab_query:
    st.header("Query Playground")
    st.caption("Streams a grounded answer over Server-Sent Events from POST /rag/query.")

    files = [f for f in list_files() if f.get("indexingStatus") == "INDEXED"]
    if files:
        multi = st.multiselect(
            "Scope to files (INDEXED only; empty = search whole corpus)",
            options=[f"{f.get('fileId')} — {f.get('filename')}" for f in files],
        )
        file_ids = [int(m.split(" — ")[0]) for m in multi] or None
    else:
        file_ids = None
        st.caption("No INDEXED files yet — searching the whole corpus (empty scope).")

    question = st.text_area("Your question", height=100)
    if st.button("Ask (stream)", type="primary") and question.strip():
        body = {
            "question": question.strip(),
            "top_k": top_k,
            "score_threshold": score_threshold,
        }
        if file_ids is not None:
            body["file_ids"] = file_ids

        try:
            with requests.post(
                f"{API_BASE}/rag/query",
                json=body,
headers=auth_headers(api_token),
                stream=True,
                timeout=120,
            ) as resp:
                resp.raise_for_status()
                answer = ""
                placeholder = st.empty()
                sources = []
                diagnostics = None
                for raw_line in resp.iter_lines(decode_unicode=True):
                    if not raw_line or not raw_line.startswith("data: "):
                        continue
                    event = json.loads(raw_line[len("data: "):])
                    if event.get("type") == "token":
                        answer += event.get("text", "")
                        placeholder.markdown(answer)
                    elif event.get("type") == "final":
                        sources = event.get("sources", [])
                        diagnostics = event.get("diagnostics", {})
                        placeholder.markdown(answer)

                if diagnostics and diagnostics.get("insufficient_evidence"):
                    st.warning("Insufficient evidence — the model abstained from answering.")

                if sources:
                    with st.expander("Sources"):
                        st.dataframe(pd.DataFrame(sources))
                if diagnostics:
                    with st.expander("Diagnostics"):
                        st.json(diagnostics)
        except requests.HTTPError as exc:
            st.error(f"Query failed: {api_error(exc.response)}")
        except Exception as exc:
            st.error(f"Query failed: {exc}")