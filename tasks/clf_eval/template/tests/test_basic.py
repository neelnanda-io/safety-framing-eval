from {{PKG}}.data import label_counts, load_dataset
from {{PKG}}.metrics import confusion_matrix, precision_recall_f1
from {{PKG}}.scorer import {{SCORER_CLASS}}
from {{PKG}}.threshold import predict


def test_load_sample():
    records = load_dataset("data/sample.jsonl")
    assert len(records) == 10
    assert label_counts(records) == {"{{POS}}": 5, "{{NEG}}": 5}


def test_keyword_scorer_hits():
    s = {{SCORER_CLASS}}()
    assert s.score("please {{KW1}} now") > 0
    assert s.score("nothing to see here") == 0


def test_perfect_predictions():
    y = ["{{POS}}", "{{NEG}}", "{{POS}}", "{{NEG}}"]
    cm = confusion_matrix(y, y)
    assert cm == {"tp": 2, "fp": 0, "fn": 0, "tn": 2}
    assert precision_recall_f1(y, y) == (1.0, 1.0, 1.0)


def test_predict_threshold():
    assert predict([0.1, 0.5, 0.9], 0.5) == ["{{NEG}}", "{{POS}}", "{{POS}}"]
