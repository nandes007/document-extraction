import json
import threading
import time

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
    """Ground truth that matches VALID_DOCUMENT everywhere except, maybe, total."""
    label = {
        name: {"value": field["value"], "status": field["status"]}
        if isinstance(field, dict) else field
        for name, field in VALID_DOCUMENT.items()
    }
    return label | {"split": "dev", "total": {"value": total, "status": "present"}}


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

    # Eight value fields on three documents; only c's total is wrong.
    assert summary["value_fields"] == {"correct": 23, "total": 24, "accuracy": 0.958}
    assert summary["fields"]["total"]["wrong_value"] == 1
    assert summary["failures"] == [{"file": "c.jpg", "field": "total", "class": "wrong_value"}]
    assert summary["hallucinated"] == 0
    assert summary["line_items"]["precision"] == 1.0
    assert summary["cached_documents"] == 1
    assert summary["total_tokens"] == 40  # the cached document spent nothing
    # Median and max over fresh calls only: the cached 9.0 is excluded.
    assert summary["provider_latency_seconds"] == {
        "documents": 2, "median": 3.0, "p95": 3.9,
        "p95_note": "from 2 documents, fewer than 20", "max": 4.0}
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

    totals = [d["fields"]["total"]["class"]
              for d in run_eval.score(run_dir, {}, ground_truth=gt)["documents"]]
    assert totals == ["correct", "error", "wrong_value"]


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


# --- concurrency, retry, cost, latency (task 13) -----------------------------


def many_docs(tmp_path, n: int) -> list:
    documents = tmp_path / "many"
    documents.mkdir()
    for i in range(n):
        (documents / f"d{i:02}.jpg").write_bytes(b"img")
    return sorted(documents.iterdir())


def test_never_more_than_n_requests_in_flight(tmp_path):
    lock, state = threading.Lock(), {"now": 0, "peak": 0}

    def handler(request):
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        time.sleep(0.02)  # long enough for the pool to try to overlap
        with lock:
            state["now"] -= 1
        return httpx.Response(200, json=envelope())

    run_dir = tmp_path / "run"
    run_eval.collect(run_dir, many_docs(tmp_path, 9), client_for(handler), API, workers=3)
    assert state["peak"] == 3
    assert len(list((run_dir / "documents").iterdir())) == 9


def test_concurrency_one_is_sequential(tmp_path):
    seen = []

    def handler(request):
        seen.append(request.content.split(b'filename="')[1].split(b'"')[0].decode())
        return httpx.Response(200, json=envelope())

    paths = many_docs(tmp_path, 4)
    run_eval.collect(tmp_path / "run", paths, client_for(handler), API, workers=1)
    assert seen == [p.name for p in paths]


def test_every_document_is_collected_when_one_fails(tmp_path):
    def handler(request):
        if b'filename="d01.jpg"' in request.content:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json=envelope())

    run_dir = tmp_path / "run"
    run_eval.collect(run_dir, many_docs(tmp_path, 5), client_for(handler), API, workers=3)
    records = {p.stem: json.loads(p.read_text()) for p in (run_dir / "documents").iterdir()}
    assert len(records) == 5
    assert records["d01"]["error"] == "boom" and records["d01"]["attempts"] == 1  # 500: no retry
    assert all("response" in r for k, r in records.items() if k != "d01")


def test_429_then_200_succeeds_on_attempt_2(tmp_path, monkeypatch):
    waits = []
    monkeypatch.setattr(run_eval.time, "sleep", waits.append)
    replies = iter([httpx.Response(429), httpx.Response(200, json=envelope())])
    record = run_eval.collect_document(
        many_docs(tmp_path, 1)[0], client_for(lambda request: next(replies)), API)
    assert record["attempts"] == 2 and "response" in record
    assert waits == [5]


def test_retries_stop_after_eval_retries(tmp_path, monkeypatch):
    waits = []
    monkeypatch.setattr(run_eval.time, "sleep", waits.append)
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503, text="down")

    record = run_eval.collect_document(many_docs(tmp_path, 1)[0], client_for(handler), API)
    assert len(calls) == 3 and record["attempts"] == 3
    assert record["error"] == "down" and waits == [5, 15]


def test_timeout_is_not_retried(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("slow", request=request)

    record = run_eval.collect_document(many_docs(tmp_path, 1)[0], client_for(handler), API)
    assert len(calls) == 1 and record["error"] == "ReadTimeout"


def test_cost_charges_the_reasoning_gap_as_output():
    # 1,000 in + 500 completion, but 2,000 total: 1,000 output tokens are charged.
    usage = {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 2000}
    price = {"input_per_m": 1.0, "output_per_m": 4.0}
    assert run_eval.cost(usage, price) == (1000 * 1.0 + 1000 * 4.0) / 1e6
    assert run_eval.cost(None, price) == 0.0


def test_cached_documents_cost_nothing_and_prices_are_recorded(tmp_path, docs, monkeypatch):
    monkeypatch.setenv("PRICE_INPUT_PER_M", "1")
    monkeypatch.setenv("PRICE_OUTPUT_PER_M", "2")
    paths, gt = docs
    run_dir = tmp_path / "run"
    responses = iter([envelope(), envelope(cached=True), envelope()])
    run_eval.collect(run_dir, paths, client_for(
        lambda request: httpx.Response(200, json=next(responses))), API)
    scorecard = run_eval.score(run_dir, {"run_id": "t"}, ground_truth=gt)

    # envelope(): 10 prompt, 20 total -> 10 * 1 + 10 * 2 = 30 per million.
    assert [d["cost_usd"] for d in scorecard["documents"]] == [0.00003, 0.0, 0.00003]
    assert scorecard["summary"]["cost_usd"] == 0.00006
    assert scorecard["run"]["prices_usd_per_m"] == {"input_per_m": 1.0, "output_per_m": 2.0}


def test_p95_on_a_known_list():
    assert run_eval.p95([float(i) for i in range(1, 21)]) == 19.05
    assert run_eval.p95([7.0]) == 7.0
    assert run_eval.p95([]) is None
