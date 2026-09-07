"""
backend/tests/integration/routes/conftest.py

Shared fixtures for the route-level integration tests (system / rag-metrics).

Replicates the security group's in-memory SQLite + real-JWT setup locally so
the routes directory (a sibling of tests/integration/security) does not reach
into a sibling conftest. `real_jwt_db_only` overrides only get_db so the REAL
get_current_user dependency chain runs against a signed token.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from app.database import Base, get_db
from app.database.db_models import User

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
    user = User(
        id=1,
        email="metrics@test.com",
        hashed_password="pw",
        status="active",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def real_jwt_db_only(seeded, db_session):
    """Override only get_db so the REAL JWT dependency chain runs."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield {"db": db_session, "user": seeded}
    app.dependency_overrides.pop(get_db, None)