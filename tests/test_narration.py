from observateur_actif.narration import build_narration_text, build_srt, export_narration
from observateur_actif.storyboard import DocumentaryProject


def make_project():
    return DocumentaryProject.model_validate({
        "title": "Mystères du Wassoulou",
        "target_duration_minutes": 10,
        "scenes": [
            {"id": "s1", "duration_seconds": 5, "narration": "La nuit tombe.",
             "video_prompt": "Moving night shot", "motion_description": "La caméra avance.",
             "claim_status": "legend"},
            {"id": "s2", "duration_seconds": 7, "narration": "Le vent se lève.",
             "video_prompt": "Moving trees", "motion_description": "Les arbres bougent.",
             "claim_status": "hypothesis"}
        ]
    })


def test_narration_text_keeps_scene_order_and_voice_direction():
    text = build_narration_text(make_project())
    assert "voix" in text.lower()
    assert text.index("La nuit tombe.") < text.index("Le vent se lève.")


def test_srt_uses_cumulative_scene_durations():
    srt = build_srt(make_project())
    assert "00:00:00,000 --> 00:00:05,000" in srt
    assert "00:00:05,000 --> 00:00:12,000" in srt
    assert "Le vent se lève." in srt


def test_export_narration_writes_both_files(tmp_path):
    text_path, srt_path = export_narration(make_project(), tmp_path / "voice.txt", tmp_path / "subs.srt")
    assert text_path.read_text(encoding="utf-8").startswith("DOCUMENTAIRE")
    assert "00:00:05,000" in srt_path.read_text(encoding="utf-8")
