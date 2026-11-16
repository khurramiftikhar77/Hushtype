from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from hushtype.engine import Engine
from hushtype.settings import Settings
from hushtype.store import Store


class FakeRecorder:
    level = 0.5

    def __init__(self, seconds=2.0):
        self.seconds = seconds

    def start_stream(self):
        pass

    def close(self):
        pass

    def begin(self):
        pass

    def cancel(self):
        pass

    def end(self):
        return np.zeros(int(16000 * self.seconds), dtype=np.float32)


class FakeModel:
    detected = {"ur": 0.6, "hi": 0.3, "en": 0.1}

    def __init__(self, name):
        self.name = name

    def detect(self, audio):
        return dict(FakeModel.detected)

    def transcribe(self, audio, language, vocabulary=None):
        return {"en": "um, thanks for sharing this, new paragraph. Khurram",
                "ur": "السلام علیکم", "pa": "کی حال اے", "ar": "مرحبا"}[language]


class FakeHotkeys:
    def __init__(self, *a):
        self.args = a

    def start(self):
        pass

    def stop(self):
        pass


@pytest.fixture
def env(tmp_path):
    settings = Settings(tmp_path / "settings.json")
    settings.update({"auto_paste": True})  # most tests check the paste path
    store = Store(tmp_path / "db.sqlite")
    pasted, focused = [], []
    loaded = []
    window = {"title": "Feed | LinkedIn - Google Chrome", "exe": "chrome.exe"}

    def factory(name, *a):
        loaded.append(name)
        return FakeModel(name)

    eng = Engine(settings, store,
                 recorder_factory=lambda mic, pre: FakeRecorder(),
                 transcriber_factory=factory,
                 hotkeys_factory=lambda *a: FakeHotkeys(*a),
                 paste=lambda text, keep=True: pasted.append(text),
                 copy=lambda text: pasted.append("COPY:" + text),
                 foreground=lambda: (42, window["title"], window["exe"]),
                 focus=focused.append,
                 model_on_disk=lambda name: True)
    eng.start()
    return eng, settings, store, pasted, focused, loaded, window


def run(eng):
    """Process queued jobs synchronously."""
    while not eng._jobs.empty():
        job = eng._jobs.get()
        eng._process(job)


def test_full_dictation_flow(env):
    eng, settings, store, pasted, focused, loaded, _ = env
    assert eng.live()["state"] == "idle"
    eng.begin_recording()
    assert eng.live()["state"] == "recording"
    eng.finish_recording()
    assert eng.live()["state"] == "working"
    run(eng)
    assert pasted == ["Thanks for sharing this,\n\nKhurram "]
    assert focused == [42]
    item = store.last()
    assert item["text"] == "Thanks for sharing this,\n\nKhurram"
    assert item["app"] == "Chrome · LinkedIn"
    assert item["project_id"] == 1
    assert eng.live()["flash"]["text"].startswith("Pasted")


def test_rule_routes_to_project_and_its_language(env):
    eng, settings, store, pasted, *_ , window = env
    poetry = store.create_project("Poetry", language="ur", remove_fillers=False, capitalize=False,
                                  rules=["whatsapp"])
    window.update(title="WhatsApp", exe="WhatsApp.exe")
    eng.begin_recording()
    assert eng.live()["language"] == "ur"
    eng.finish_recording()
    run(eng)
    assert pasted[-1] == "السلام علیکم "
    assert store.last()["project_id"] == poetry["id"]
    assert store.last()["language"] == "ur"


def test_active_project_used_when_no_rule(env):
    eng, settings, store, *_ = env
    email = store.create_project("Email")
    settings.update({"active_project": email["id"]})
    eng.begin_recording()
    eng.finish_recording()
    run(eng)
    assert store.last()["project_id"] == email["id"]


def test_short_recording_is_ignored(env):
    eng, settings, store, pasted, *_ = env
    eng.recorder.seconds = 0.1
    eng.begin_recording()
    eng.finish_recording()
    assert eng.live()["state"] == "idle"
    assert eng._jobs.empty()


def test_cancel_discards(env):
    eng, settings, store, pasted, *_ = env
    eng.begin_recording()
    eng.cancel_recording()
    assert eng.live()["state"] == "idle"
    assert eng._jobs.empty()


def test_toggle_language_and_repaste(env):
    eng, settings, store, pasted, *_ = env
    eng.toggle_language()
    assert store.project(1)["language"] == "ur"
    eng.toggle_language()
    assert store.project(1)["language"] == "pa"
    eng.toggle_language()
    assert store.project(1)["language"] == "mix"
    eng.toggle_language()
    assert store.project(1)["language"] == "auto"
    eng.toggle_language()
    assert store.project(1)["language"] == "en"
    eng.repaste()
    assert pasted == []  # nothing yet
    eng.begin_recording(); eng.finish_recording(); run(eng)
    eng.repaste()
    assert len(pasted) == 2 and pasted[0] == pasted[1]


def test_history_can_be_turned_off(env):
    eng, settings, store, pasted, *_ = env
    settings.update({"save_history": False})
    eng.begin_recording(); eng.finish_recording(); run(eng)
    assert pasted and store.last() is None


def test_weekly_cleanup_prompt(env):
    eng, settings, store, *_ = env
    old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    store.add(project_id=1, language="en", duration=1, process_time=1, text="old", raw_text="old", created_at=old)
    store.add(project_id=1, language="en", duration=1, process_time=1, text="new", raw_text="new")
    assert eng.cleanup_due() == 0  # first prompt comes a week after first run
    settings.update({"last_review": old})
    assert eng.cleanup_due() == 1
    assert eng.cleanup(delete=True) == 1
    assert [d["text"] for d in store.dictations()] == ["new"]
    assert eng.cleanup_due() == 0  # asked again only next week


def test_delete_project_moves_items_to_inbox(env):
    eng, settings, store, *_ = env
    p = store.create_project("Work")
    store.add(project_id=p["id"], language="en", duration=1, process_time=1, text="x", raw_text="x")
    store.delete_project(p["id"])
    assert store.last()["project_id"] == 1
    with pytest.raises(ValueError):
        store.delete_project(1)


def test_mic_button_copies_instead_of_pasting(env):
    eng, settings, store, pasted, focused, *_ , window = env
    store.create_project("Email", rules=["chrome"])  # rules must not apply to the button
    eng.begin_recording(from_app=True)
    eng.finish_recording()
    run(eng)
    assert pasted == ["COPY:Thanks for sharing this,\n\nKhurram "]
    assert focused == []
    assert store.last()["app"] == "Hushtype" and store.last()["project_id"] == 1


def test_copy_only_mode(env):
    eng, settings, store, pasted, focused, *_ = env
    settings.update({"auto_paste": False})
    eng.begin_recording(); eng.finish_recording(); run(eng)
    assert pasted == ["COPY:Thanks for sharing this,\n\nKhurram "]
    assert focused == []
    assert "Ctrl+V" in eng.live()["flash"]["text"]


def test_download_progress_is_reported(tmp_path):
    import threading
    import time as _t

    settings = Settings(tmp_path / "s.json")
    store = Store(tmp_path / "d.db")
    size = {"n": 0}
    release = threading.Event()

    def slow_model(name, *a):
        for _ in range(20):
            size["n"] += 50_000_000
            _t.sleep(0.05)
        release.wait(2)
        return FakeModel(name)

    eng = Engine(settings, store, recorder_factory=lambda *a: FakeRecorder(), transcriber_factory=slow_model,
                 hotkeys_factory=lambda *a: FakeHotkeys(*a), model_on_disk=lambda n: False,
                 model_bytes=lambda n: size["n"])
    t = threading.Thread(target=eng.get_model, args=("en",)); t.start()
    _t.sleep(0.8)
    d = eng.live()["downloads"]["en"]
    assert d["total"] == 484_000_000 and 0 < d["done"] <= d["total"]
    release.set(); t.join()
    assert eng.live()["downloads"] == {}


def test_recording_stops_at_the_time_limit(env):
    import time as _t
    eng, settings, store, pasted, *_ = env
    settings.update({"max_seconds": 0.3})
    eng.begin_recording()
    assert eng.live()["max_seconds"] == 0.3
    for _ in range(40):  # the engine's own worker transcribes it
        if pasted:
            break
        _t.sleep(0.05)
    assert pasted, "recording was not stopped at the limit"
    assert eng.live()["state"] != "recording"


def test_auto_detects_urdu_and_english(env):
    eng, settings, store, pasted, *_ = env
    store.update_project(1, language="auto")
    FakeModel.detected = {"ur": 0.5, "hi": 0.3, "en": 0.2}
    eng.begin_recording(); eng.finish_recording(); run(eng)
    assert store.last()["language"] == "ur"
    assert "Urdu" in eng.live()["flash"]["text"]
    FakeModel.detected = {"en": 0.9, "ur": 0.05}
    eng.begin_recording(); eng.finish_recording(); run(eng)
    assert store.last()["language"] == "en"
    settings.update({"auto_other": "pa"})
    FakeModel.detected = {"hi": 0.8, "en": 0.1}  # Urdu speech is often labelled Hindi
    eng.begin_recording(); eng.finish_recording(); run(eng)
    assert store.last()["language"] == "pa"
    FakeModel.detected = {"ur": 0.6, "hi": 0.3, "en": 0.1}


def test_learns_from_history_edit_and_applies_it(env):
    eng, settings, store, pasted, *_ = env
    eng.begin_recording(); eng.finish_recording(); run(eng)
    item = store.last()
    fixes = eng.learn_from_edit(item["text"], item["text"].replace("Khurram", "Khurram Iftikhar").replace("Thanks", "Thanks"))
    assert fixes == []  # adding words is not a correction
    fixes = eng.learn_from_edit("Thanks for sharing this, Khuram", "Thanks for sharing this, Khurram")
    assert fixes == [("khuram", "Khurram")]
    assert settings["learned_replacements"] == {"khuram": "Khurram"}
    model = eng.get_model("en")
    model.transcribe = lambda audio, language, vocabulary=None: "Thanks, Khuram"
    eng.begin_recording(); eng.finish_recording(); run(eng)
    assert store.last()["text"] == "Thanks, Khurram"


def test_learns_names_after_three_uses(env):
    eng, settings, store, *_ = env
    model = eng.get_model("en")
    seen = []
    def fake(audio, language, vocabulary=None):
        seen.append(list(vocabulary or []))
        return "Great to meet Zainab at the event."
    model.transcribe = fake
    for _ in range(3):
        eng.begin_recording(); eng.finish_recording(); run(eng)
    assert "Zainab" in settings["learned_words"]
    eng.begin_recording(); eng.finish_recording(); run(eng)
    assert "Zainab" in seen[-1]  # now passed to Whisper as a known word


def test_mix_mode_transcribes_each_piece_in_its_language(env):
    eng, settings, store, pasted, *_ = env
    store.update_project(1, language="mix")
    pieces = [np.zeros(16000 * 3, dtype=np.float32), np.ones(16000 * 3, dtype=np.float32)]
    eng.split_for_mix = lambda audio: pieces
    answers = iter([{"en": 0.95}, {"ur": 0.8, "en": 0.1}])
    FakeModel.detect = lambda self, audio: next(answers)
    eng.begin_recording(); eng.finish_recording(); run(eng)
    item = store.last()
    assert item["language"] == "mix"
    assert item["text"].startswith("Thanks for sharing this,") and item["text"].endswith("السلام علیکم")
    FakeModel.detect = lambda self, audio: dict(FakeModel.detected)


def test_autodetect_switch_remembers_the_language(env):
    eng, settings, store, *_ = env
    store.update_project(1, language="ur")
    eng.set_autodetect(True)
    assert store.project(1)["language"] == "auto"
    eng.set_autodetect(False)
    assert store.project(1)["language"] == "ur"


def test_language_cycle_includes_mix(env):
    eng, settings, store, *_ = env
    settings.update({"languages_enabled": ["en"]})
    store.update_project(1, language="en")
    eng.toggle_language()
    assert store.project(1)["language"] == "mix"
    eng.toggle_language()
    assert store.project(1)["language"] == "auto"


def test_copy_only_is_the_default(tmp_path):
    assert Settings(tmp_path / "fresh.json")["auto_paste"] is False


def test_repaste_copies_when_auto_paste_is_off(env):
    eng, settings, store, pasted, *_ = env
    settings.update({"auto_paste": False})
    eng.begin_recording(); eng.finish_recording(); run(eng)
    eng.repaste()
    assert pasted[-1].startswith("COPY:") and len(pasted) == 2
    assert "Copied again" in eng.live()["flash"]["text"]


def test_settings_migrate_old_shortcut(tmp_path):
    import json
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"hotkey": "alt_r", "auto_paste": True}))
    s = Settings(path)
    assert s["hotkey"] == "alt_r+space"
    assert s["auto_paste"] is False  # v3 migration: copy only
    path.write_text(json.dumps({"hotkey": "f9"}))
    assert Settings(path)["hotkey"] == "f9"


def test_punjabi_uses_urdu_model_and_cycles(env):
    eng, settings, store, pasted, focused, loaded, _ = env
    store.update_project(1, language="pa")
    assert eng.model_name("pa") == settings["ur_model"]
    model = eng.get_model("pa")
    assert eng.get_model("ur") is model  # one shared model, loaded once
    eng.toggle_language()
    assert store.project(1)["language"] == "mix"
    eng.toggle_language(); eng.toggle_language(); eng.toggle_language(); eng.toggle_language()
    assert store.project(1)["language"] == "pa"


def test_punjabi_dictation_saved_as_punjabi(env):
    eng, settings, store, pasted, *_ = env
    model = eng.get_model("pa")
    model.transcribe = lambda audio, language, vocabulary=None: {"en": "hello", "ur": "اردو", "pa": "کی حال اے"}[language]
    store.update_project(1, language="pa")
    eng.begin_recording(); eng.finish_recording(); run(eng)
    assert pasted[-1] == "کی حال اے "
    assert store.last()["language"] == "pa"


def test_languages_share_models_by_name_and_can_be_removed(env, tmp_path):
    eng, settings, store, pasted, focused, loaded, _ = env
    deleted = []
    eng._delete_model = lambda name: deleted.append(name) or 123
    settings.update({"languages_enabled": ["en", "ur", "pa", "ar"]})
    before = len(loaded)
    eng.get_model("ar")  # Arabic uses large-v3-turbo by default, already loaded for Urdu
    eng.get_model("ur")
    assert len(loaded) - before <= 1
    assert eng.get_model("ar") is eng.get_model("ur")
    assert eng.remove_model("ar") == 123 and deleted == ["large-v3-turbo"]
    assert "large-v3-turbo" not in eng.models


def test_language_cycle_uses_enabled_languages(env):
    eng, settings, store, *_ = env
    settings.update({"languages_enabled": ["en", "ar"]})
    store.update_project(1, language="en")
    eng.toggle_language()
    assert store.project(1)["language"] == "ar"
    eng.toggle_language()
    assert store.project(1)["language"] == "mix"


def test_auto_picks_other_enabled_language(env):
    eng, settings, store, *_ = env
    settings.update({"languages_enabled": ["en", "ur", "ar"]})
    FakeModel.detected = {"ar": 0.7, "ur": 0.1, "en": 0.1}
    assert eng.detect_language(None) == "ar"
    FakeModel.detected = {"ur": 0.5, "hi": 0.3, "ar": 0.1, "en": 0.1}
    assert eng.detect_language(None) == "ur"
    settings.update({"languages_enabled": ["en", "ur"]})
    FakeModel.detected = {"ar": 0.7, "ur": 0.1, "en": 0.1}
    assert eng.detect_language(None) == "ur"  # Arabic not enabled
    FakeModel.detected = {"ur": 0.6, "hi": 0.3, "en": 0.1}


def test_email_detection():
    from hushtype.engine import is_email
    assert is_email("Outlook", "Inbox") and is_email("Chrome · Gmail", "Inbox")
    assert is_email("Notepad", "Email")
    assert not is_email("Chrome · LinkedIn", "Inbox")


def test_boost_quiet_only_raises_quiet_audio():
    from hushtype.engine import boost_quiet
    quiet = (np.sin(np.linspace(0, 100, 16000)) * 0.02).astype(np.float32)
    loud = (np.sin(np.linspace(0, 100, 16000)) * 0.6).astype(np.float32)
    assert abs(float(np.max(np.abs(boost_quiet(quiet)))) - 0.5) < 0.01
    assert boost_quiet(loud) is loud
    assert boost_quiet(np.zeros(100, dtype=np.float32)).max() == 0
