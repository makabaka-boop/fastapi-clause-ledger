import os
import tempfile

# 在导入 app 之前指向测试数据库
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["CLAUSE_LEDGER_DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def document(client):
    resp = client.post(
        "/api/v1/documents",
        json={"title": "采购管理制度", "source_department": "合规部", "version_no": "v1"},
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def clause(client, document):
    resp = client.post(
        f"/api/v1/documents/{document['id']}/clauses/batch",
        json={"clauses": [{"clause_no": "1.1", "clause_text": "供应商准入须审批"}]},
    )
    assert resp.status_code == 201
    return resp.json()[0]
