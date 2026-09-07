"""
backend/tests/integration/security/conftest.py

Shared fixtures for the Phase 7 security test group.

Tenant topology:
    Alice   (id 1, active)   owns file 10 (ACTIVE + INDEXED)
    Bob     (id 2, active)   owns file 20 (ACTIVE + INDEXED)
    Zoe     (id 3, disabled) owns file 30 (ACTIVE + INDEXED)

`authenticated` overrides get_db + get_current_user (fast identity swap).
`real_jwt_db_only` overrides only get_db so tests can exercise the REAL
get_current_user / JWT dependency chain against a real signed token.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from main import app
from app.database import Base, get_db
from app.auth.auth_dependencies import get_current_user
from app.database.db_models import FileMetadata, User
from app.schemas.enums import FileStatus, IndexingStatus
from app.core.security import create_access_token

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

client = TestClient(app)

# Stable users / files for the security topology.
ALICE = 1
BOB = 2
ZOE = 3
ALICE_FILE = 10
BOB_FILE = 20
ZOE_FILE = 30


def _make_user(db: Session, user_id: int, status: str) -> User:
    user = User(
        id=user_id,
        email=f"u{user_id}@test.com",
        hashed_password="pw",
        status=status,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_file(db: Session, fileid: int, userid: int) -> FileMetadata:
    file = FileMetadata(
        fileid=fileid,
        s3_key=f"uploads/f{fileid}.pdf",
        filename=f"f{fileid}.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        status=FileStatus.ACTIVE.value,
        userid=userid,
        active_index_version=1,
        corpus_revision=0,
        indexing_status=IndexingStatus.INDEXED.value,
        index_version=1,
    )
    db.add(file)
    db.commit()
    db.refresh(file)
    return file


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def seeded(db_session):
    _make_user(db_session, ALICE, "active")
    _make_user(db_session, BOB, "active")
    _make_user(db_session, ZOE, "disabled")
    _make_file(db_session, ALICE_FILE, ALICE)
    _make_file(db_session, BOB_FILE, BOB)
    _make_file(db_session, ZOE_FILE, ZOE)


@pytest.fixture
def authenticated(seeded, db_session):
    """Override both identity deps; requests run as ALICE."""
    alice = db_session.query(User).filter_by(id=ALICE).first()

    def override_get_db():
        yield db_session

    def override_get_current_user():
        return alice

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield {"db": db_session, "user": alice}
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def real_jwt_db_only(seeded, db_session):
    """Override only get_db so the REAL JWT dependency runs against the DB."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield {"db": db_session}
    app.dependency_overrides.pop(get_db, None)


def alice_token() -> str:
    return create_access_token(user_id=ALICE)


def bob_token() -> str:
    return create_access_token(user_id=BOB)


def zoe_token() -> str:
    return create_access_token(user_id=ZOE)