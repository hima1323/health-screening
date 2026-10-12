"""Verifier self-check: python src/test_reasoner.py"""
import copy

from reasoner import rule_check, template, verify

REC = {"label": "high", "confidence": 0.82, "probability_high": 0.82, "quality": {"ecg": 1.0, "eye": 0.7},
       "low_quality_modalities": [], "top_features": [
           {"feature": "eye_pupil_mean", "description": "pupil diameter", "unit": "mm", "value": 4.119, "z": 1.52,
            "shap": 0.41, "pushes_toward": "high", "learned_direction_high_load": "+",
            "literature_direction_high_load": "+"},
           {"feature": "ecg_pnn50", "description": "pNN50 heart-rate variability", "unit": "%", "value": 22.7,
            "z": 0.8, "shap": -0.12, "pushes_toward": "low", "learned_direction_high_load": "-",
            "literature_direction_high_load": "-"}]}

s, c = rule_check(REC)
assert [f["feature"] for f in s] == ["eye_pupil_mean"] and s[0]["rule_agrees"] is True
assert [f["feature"] for f in c] == ["ecg_pnn50"] and c[0]["rule_agrees"] is False
good = template(REC, s, c)
assert verify(good, REC) == [], verify(good, REC)

bad = copy.deepcopy(good); bad["conclusion"] = "low"
assert any("conclusion" in e for e in verify(bad, REC))                       # label change rejected
bad = copy.deepcopy(good); bad["evidence"][0]["statement"] = "pupil grew by 37 percent"
assert any("37" in e for e in verify(bad, REC))                               # invented number rejected
bad = copy.deepcopy(good); bad["evidence"][0]["statement"] = "ecg_hr also rose"
assert any("ecg_hr" in e for e in verify(bad, REC))                           # uncited feature rejected
bad = copy.deepcopy(good); bad["evidence"][0]["z"] = 2.5
assert any(".z" in e for e in verify(bad, REC))                               # wrong value rejected
ok = copy.deepcopy(good); ok["evidence"][0]["statement"] = "pupil diameter 4.12 mm, z 1.5"
assert verify(ok, REC) == [], verify(ok, REC)                                 # rounding of record numbers is fine
low = copy.deepcopy(REC); low["confidence"] = 0.55
assert any("abstain" in e for e in verify(dict(good, confidence=0.55), low))  # must abstain when unsure
print("verifier ok")
