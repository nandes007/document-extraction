import pytest

from evals.run_eval import classify

PRESENT = {"value": 161700, "status": "present"}
ABSENT = {"value": None, "status": "not_present"}
UNREADABLE = {"value": None, "status": "unreadable"}


def test_same_value_is_correct():
    assert classify(PRESENT, dict(PRESENT)) == "correct"


def test_different_value_is_wrong():
    assert classify(PRESENT, {"value": 161000, "status": "present"}) == "wrong_value"


@pytest.mark.parametrize("actual", [ABSENT, UNREADABLE])
def test_abstaining_on_a_real_value_is_missed(actual):
    assert classify(PRESENT, actual) == "missed"


@pytest.mark.parametrize("expected", [ABSENT, UNREADABLE])
def test_inventing_a_value_is_hallucinated(expected):
    assert classify(expected, PRESENT) == "hallucinated"


@pytest.mark.parametrize("expected", [ABSENT, UNREADABLE])
@pytest.mark.parametrize("actual", [ABSENT, UNREADABLE])
def test_both_abstaining_is_correct(expected, actual):
    """Nothing missed, nothing invented — the two statuses need not match."""
    assert classify(expected, actual) == "correct"


def test_zero_is_a_value_not_an_absence():
    """A printed `Diskon: 0` is present with value 0, per the labelling rules."""
    zero = {"value": 0, "status": "present"}
    assert classify(zero, dict(zero)) == "correct"
    assert classify(zero, ABSENT) == "missed"
    assert classify(ABSENT, zero) == "hallucinated"
