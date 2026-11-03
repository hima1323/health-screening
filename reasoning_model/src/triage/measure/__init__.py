"""Measurement agents: recordings -> evidence-record measurements (value, readings, error margin, quality).

measure_recordings() runs every agent for which a recording was given. One heart rate goes into the record: a contact
ECG / finger-PPG file when its quality passes, otherwise the camera (rPPG); when both exist the other one and their
difference are kept in the diagnostics.
"""


def measure_recordings(video=None, thermal=None, thermal_fps=None, thermal_meta=None, contact=None,
                       contact_kind="ecg", contact_fs=None, contact_column=None, devices=None, min_quality=0.5):
    """-> (measurements, flags, diagnostics). `devices`: {"spo2": [r1, r2], "sbp": [...], "dbp": [...]}."""
    from triage.measure import devices as dev
    from triage.measure import hr_rppg, thermal_vitals

    hr, flags, diag = [], [], {}
    if video:
        m, d = hr_rppg.measure(video)
        diag["video"] = d
        hr.append(m)
        if not d.get("face_found", True):
            flags.append("face_not_found")
    if contact:
        m, d = dev.measure(contact, contact_kind, contact_fs, contact_column)
        diag["contact"] = d
        hr.insert(0, m)
    out = []
    if hr:
        usable = [m for m in hr if m["value"] is not None and m["quality"] >= min_quality]
        chosen = usable[0] if usable else hr[0]
        out.append(chosen)
        others = [m for m in hr if m is not chosen and m["value"] is not None]
        if others and chosen["value"] is not None:
            diag["heart_rate_sources"] = {"used": chosen["source"], "other": others[0]["source"],
                                          "difference_bpm": round(abs(chosen["value"] - others[0]["value"]), 1)}
    if thermal:
        ms, d = thermal_vitals.measure(thermal, thermal_fps, thermal_meta)
        diag["thermal"] = d
        out += ms
    for name, (unit, readings) in (devices or {}).items():
        if readings and any(r is not None for r in readings):
            out.append(dev.device_reading(name, readings, unit))
    return out, flags, diag
