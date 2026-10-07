import json

import httpx
import pytest

from evals import run_eval
from tests.test_schema import VALID_DOCUMENT  # total 161700

API = "http://api.test"


def envelope(cached: bool = False, latency: float = 2.0) -> dict:
    meta = {"model": "m", "prompt_version": "v1", "attempts": 1,
            "latency_seconds": latency, "cached": cached,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 20}}
    return {"document": VALID_DOCUMENT, "meta": meta}


def truth(total: int) -> dict:
    return {"split": "dev", "document_type": "food",
            "total": {"value": total, "status": "present"}}


@pytest.fixture
def docs(tmp_path):
    """Three fake documents with ground truth: two match VALID_DOCUMENT, one doesn't."""
    documents, gt = tmp_path / "documents", tmp_path / "gt"
    documents.mkdir(), gt.mkdir()
    for stem, total in [("a", 161700), ("b", 161700), ("c", 999)]:
        (documents / f"{stem}.jpg").write_bytes(b"img")
        (gt / f"{stem}.json").write_text(json.dumps(truth(total)))
    return sorted(documents.iterdir()), gt


def client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_scoring_a_saved_run_gives_expected_counts(tmp_path, docs):
    paths, gt = docs
    run_dir = tmp_path / "run"
    responses = iter([envelope(), envelope(cached=True, latency=9.0), envelope(latency=4.0)])
    run_eval.collect(run_dir, paths, client_for(
        lambda request: httpx.Response(200, json=next(responses))), API)

    scorecard = run_eval.score(run_dir, {"run_id": "t"}, ground_truth=gt)
    summary = scorecard["summary"]

    assert summary["counts"]["correct"] == 2
    assert summary["counts"]["wrong_value"] == 1
    assert summary["cached_documents"] == 1
    assert summary["total_tokens"] == 40  # the cached document spent nothing
    # Median and max over fresh calls only: the cached 9.0 is excluded.
    assert summary["provider_latency_seconds"] == {"median": 3.0, "max": 4.0}
    assert scorecard["run"]["model"] == "m"
    assert scorecard["run"]["prompt_version"] == "v1"


def test_timeout_on_one_document_does_not_stop_the_run(tmp_path, docs):
    paths, gt = docs

    def handler(request):
        if b'filename="b.jpg"' in request.content:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, json=envelope())

    run_dir = tmp_path / "run"
    run_eval.collect(run_dir, paths, client_for(handler), API)

    saved = sorted(p.name for p in (run_dir / "documents").iterdir())
    assert saved == ["a.json", "b.json", "c.json"]
    assert json.loads((run_dir / "documents" / "b.json").read_text())["error"] == "ReadTimeout"

    classes = [d["class"] for d in run_eval.score(run_dir, {}, ground_truth=gt)["documents"]]
    assert classes == ["correct", "error", "wrong_value"]


def test_rescore_matches_original_and_makes_no_http_request(tmp_path, docs, monkeypatch):
    paths, gt = docs
    run_dir = tmp_path / "run"
    run_eval.collect(run_dir, paths, client_for(
        lambda request: httpx.Response(200, json=envelope())), API)
    original = run_eval.score(run_dir, {"run_id": "t", "started_at": "x"}, ground_truth=gt)
    (run_dir / "scorecard.json").write_text(json.dumps(original))

    def no_http(*args, **kwargs):
        raise AssertionError("rescore must not open an HTTP client")

    monkeypatch.setattr(run_eval.httpx, "Client", no_http)
    monkeypatch.setattr(run_eval, "GROUND_TRUTH", gt)
    run_eval.main(["--rescore", str(run_dir)])

    rescored = json.loads((run_dir / "scorecard.json").read_text())
    assert rescored["summary"] == original["summary"]
    assert rescored["run"]["started_at"] == "x"  # the original run block is kept


def test_unreachable_api_creates_no_run_folder(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run_eval, "RUNS", tmp_path / "runs")

    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    assert run_eval.main([], client=client_for(refuse)) == 1
    assert not (tmp_path / "runs").exists()
    assert "cannot reach API" in capsys.readouterr().err


def test_existing_run_folder_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(run_eval, "RUNS", tmp_path / "runs")
    monkeypatch.setenv("RUN_ID", "taken")
    (tmp_path / "runs" / "taken").mkdir(parents=True)

    healthy = client_for(lambda request: httpx.Response(200, json={"status": "ok"}))
    with pytest.raises(SystemExit, match="already exists"):
        run_eval.main([], client=healthy)
