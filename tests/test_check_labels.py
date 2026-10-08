import copy
import json

import pytest

from evals import check_labels

GOOD = {
    "file": "a.jpg",
    "split": "dev",
    "tags": ["printed"],
    "document_type": "food",
    "merchant_name": {"value": "Warung", "status": "present", "accept": ["WARUNG"]},
    "transaction_date": {"value": "2026-10-03", "status": "present"},
    "line_items": [{"description": "Teh", "quantity": 1, "unit_price": 5000, "amount": 5000}],
    "subtotal": {"value": None, "status": "not_present"},
    "discount": {"value": 0, "status": "present"},
    "service_charge": {"value": None, "status": "not_present"},
    "tax": {"value": None, "status": "unreadable"},
    "total": {"value": 5000, "status": "present"},
    "payment_method": {"value": "cash", "status": "present"},
}


@pytest.fixture
def data(tmp_path):
    """A temp data/ with one good document; never the real ground truth."""
    documents, gt = tmp_path / "documents", tmp_path / "ground_truth"
    documents.mkdir(), gt.mkdir()
    (documents / "a.jpg").write_bytes(b"img")
    (gt / "a.json").write_text(json.dumps(GOOD))
    return documents, gt


def problems_for(data, **changes) -> list[str]:
    documents, gt = data
    label = copy.deepcopy(GOOD) | changes
    (gt / "a.json").write_text(json.dumps(label))
    return check_labels.check(documents, gt)[0]


def test_good_label_passes_and_is_counted(data):
    problems, counts = check_labels.check(*data)
    assert problems == []
    assert counts == {("food", "dev"): 1}
    assert check_labels.main(*data) == 0


def test_document_without_label_and_label_without_document(data):
    documents, gt = data
    (documents / "b.jpg").write_bytes(b"img")
    (gt / "c.json").write_text(json.dumps(GOOD | {"file": "c.jpg"}))
    problems, _ = check_labels.check(documents, gt)
    assert "b.jpg: no ground truth file b.json" in problems
    assert any(p.startswith("c.json: file:") for p in problems)
    assert check_labels.main(documents, gt) == 1


def test_file_must_match_label_name(data):
    documents, _ = data
    (documents / "other.jpg").write_bytes(b"img")
    assert any("does not match" in p for p in problems_for(data, file="other.jpg"))


@pytest.mark.parametrize("changes, expected", [
    ({"split": "train"}, "a.json: split:"),
    ({"split": "test"}, "a.json: split:"),  # test split needs the test_ prefix
    ({"document_type": "hotel"}, "a.json: document_type:"),
    ({"tags": "printed"}, "a.json: tags:"),
    ({"total": {"value": 5000, "status": "maybe"}}, "a.json: total.status:"),
    ({"discount": {"value": 0, "status": "not_present"}}, "a.json: discount.value: must be null"),
    ({"total": {"value": None, "status": "present"}}, "a.json: total.value: null"),
    ({"total": {"value": 5000.5, "status": "present"}}, "a.json: total.value: must be an integer"),
    ({"total": {"value": "5.000", "status": "present"}}, "a.json: total.value: must be an integer"),
    ({"transaction_date": {"value": "03-10-2026", "status": "present"}}, "a.json: transaction_date.value:"),
    ({"payment_method": {"value": "gopay", "status": "present"}}, "a.json: payment_method.value:"),
    ({"merchant_name": {"value": "Warung", "status": "present", "accept": "W"}}, "a.json: merchant_name.accept:"),
    ({"line_items": [{"description": "Teh", "quantity": "1", "unit_price": None, "amount": None}]},
     "a.json: line_items[0].quantity:"),
    ({"line_items": [{"description": "Teh", "quantity": 1, "unit_price": None, "amount": 1.5}]},
     "a.json: line_items[0].amount:"),
])
def test_each_problem_names_file_and_field(data, changes, expected):
    problems = problems_for(data, **changes)
    assert any(p.startswith(expected) for p in problems), problems


def test_missing_field_is_reported(data):
    documents, gt = data
    label = copy.deepcopy(GOOD)
    del label["tax"]
    (gt / "a.json").write_text(json.dumps(label))
    assert "a.json: tax: missing" in check_labels.check(documents, gt)[0]


def test_test_prefix_with_test_split_passes(tmp_path):
    documents, gt = tmp_path / "documents", tmp_path / "ground_truth"
    documents.mkdir(), gt.mkdir()
    (documents / "test_a.pdf").write_bytes(b"pdf")
    (gt / "test_a.json").write_text(json.dumps(GOOD | {"file": "test_a.pdf", "split": "test"}))
    assert check_labels.check(documents, gt)[0] == []


def test_invalid_json_is_reported(data):
    documents, gt = data
    (gt / "a.json").write_text("{not json")
    assert check_labels.check(documents, gt)[0][0].startswith("a.json: not valid JSON")
