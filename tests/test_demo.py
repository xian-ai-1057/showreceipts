"""Demo HTTP 包裝層：每個端點的輸出與直接呼叫 Python API 完全相同。"""

from fastapi.testclient import TestClient

from demo.app import create_app
from showreceipts import Passage, ShowReceiptsConfig, postprocess

PASSAGES = [
    Passage(id="A", text="first A", source="doc.md", locator="第 1 頁", score=0.9, metadata={"k": 1}),
    Passage(id="B", text="B", source="doc.md"),
    Passage(id="A", text="second A", source="other.md"),
]
ANSWER = "x [2] y [0] z [3] w [9]。"


def test_demo_postprocess_matches_python_api() -> None:
    client = TestClient(create_app())
    config = ShowReceiptsConfig(input_marker_base=0)

    response = client.post(
        "/postprocess",
        json={
            "answer_text": ANSWER,
            "passages": [p.model_dump(mode="json") for p in PASSAGES],
            "config": config.model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    assert response.json() == postprocess(ANSWER, PASSAGES, config=config).model_dump(mode="json")
