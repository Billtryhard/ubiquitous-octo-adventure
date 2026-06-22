from datetime import date

import pytest

from portfolio_monitor.macro import (
    MacroInputs,
    MacroWeights,
    SyntheticMacroProvider,
    compute_macro_score,
    percentile_of,
    score_term_structure,
    score_vix_level,
)


def test_weights_must_sum_to_one():
    MacroWeights().validate()  # default sums to 1.0
    with pytest.raises(ValueError):
        MacroWeights(vix_level=0.5, vix_percentile=0.5, term_structure=0.5,
                     breadth=0.0, credit=0.0).validate()


def test_percentile_of():
    assert percentile_of(5, [1, 2, 3, 4]) == 100.0
    assert percentile_of(0, [1, 2, 3, 4]) == 0.0
    assert percentile_of(3, [1, 2, 3, 4, 5]) == 40.0  # two of five below


def test_vix_level_orientation():
    # Lower VIX -> higher (calmer) score
    assert score_vix_level(12) > score_vix_level(25) > score_vix_level(40)
    assert score_vix_level(12) == 100.0
    assert score_vix_level(40) == 0.0


def test_term_structure_contango_vs_backwardation():
    contango = score_term_structure(15, 18)   # VIX3M > VIX -> calm
    backward = score_term_structure(30, 25)   # VIX > VIX3M -> stress
    assert contango > backward
    assert backward < 50


def test_macro_deterministic_same_in_same_out():
    prov = SyntheticMacroProvider()
    a = compute_macro_score(prov.get_macro_inputs(date(2026, 6, 17)))
    b = compute_macro_score(prov.get_macro_inputs(date(2026, 6, 17)))
    assert a.score == b.score
    assert a.components == b.components


def test_macro_score_in_range_and_blended():
    prov = SyntheticMacroProvider()
    res = compute_macro_score(prov.get_macro_inputs(date(2026, 6, 17)))
    assert 0.0 <= res.score <= 100.0
    assert set(res.components) == {
        "vix_level", "vix_percentile", "term_structure", "breadth", "credit"
    }
    # blended score equals weighted sum of components
    expected = sum(res.components[k] * res.weights[k] for k in res.components)
    assert abs(res.score - expected) < 1e-9


def test_calm_inputs_score_high():
    inputs = MacroInputs(
        asof=date(2026, 6, 17),
        vix=12.0,
        vix3m=15.0,                       # steep contango
        vix_history_1y=[20.0] * 250,      # today's VIX far below its year
        breadth_pct=85.0,
        hyg_tlt_ratio=1.30,
        hyg_tlt_ratio_history_1y=[1.10] * 250,  # ratio near top of range
    )
    res = compute_macro_score(inputs)
    assert res.score > 80
    assert res.label == "supportive / calm"


def test_stressed_inputs_score_low():
    inputs = MacroInputs(
        asof=date(2026, 6, 17),
        vix=42.0,
        vix3m=34.0,                       # backwardation
        vix_history_1y=[18.0] * 250,      # today's VIX far above its year
        breadth_pct=15.0,
        hyg_tlt_ratio=1.05,
        hyg_tlt_ratio_history_1y=[1.25] * 250,  # ratio near bottom of range
    )
    res = compute_macro_score(inputs)
    assert res.score < 20
    assert res.label == "stressed / defensive"


def test_custom_weights_change_score():
    prov = SyntheticMacroProvider()
    inputs = prov.get_macro_inputs(date(2026, 6, 17))
    base = compute_macro_score(inputs)
    skewed = compute_macro_score(
        inputs, MacroWeights(vix_level=1.0, vix_percentile=0.0,
                             term_structure=0.0, breadth=0.0, credit=0.0)
    )
    assert skewed.score == pytest.approx(base.components["vix_level"])
