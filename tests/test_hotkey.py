from hushtype.hotkey import HotkeyLogic


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def make(**kw):
    log, clock = [], Clock()
    names = ["start", "stop", "cancel", "toggle_language", "repaste", "hands_free"]
    logic = HotkeyLogic({n: (lambda n=n: log.append(n)) for n in names}, clock=clock, **kw)
    return logic, log, clock


def hold(logic, clock, seconds):
    logic.key_down()
    clock.t += seconds
    logic.key_up()


def test_hold_records_and_stops():
    logic, log, clock = make()
    hold(logic, clock, 2.0)
    assert log == ["start", "stop"]


def test_single_tap_is_cancelled():
    logic, log, clock = make()
    hold(logic, clock, 0.1)
    assert log == ["start", "cancel"]


def test_double_tap_enters_hands_free_then_tap_stops():
    logic, log, clock = make()
    hold(logic, clock, 0.1)
    clock.t += 0.2
    hold(logic, clock, 0.1)
    assert log == ["start", "cancel", "start", "hands_free"]
    assert logic.hands_free
    clock.t += 5  # talking hands-free
    hold(logic, clock, 0.1)
    assert log[-1] == "stop"
    assert not logic.hands_free


def test_slow_taps_are_not_double_tap():
    logic, log, clock = make()
    hold(logic, clock, 0.1)
    clock.t += 1.0
    hold(logic, clock, 0.1)
    assert log == ["start", "cancel", "start", "cancel"]


def test_hands_free_can_be_disabled():
    logic, log, clock = make(hands_free=False)
    hold(logic, clock, 0.1)
    clock.t += 0.2
    hold(logic, clock, 0.1)
    assert "hands_free" not in log


def test_key_plus_l_toggles_language_without_dictating():
    logic, log, clock = make()
    logic.key_down()
    assert logic.combo("l")
    clock.t += 1.0
    logic.key_up()
    assert log == ["start", "cancel", "toggle_language"]


def test_key_plus_v_repastes_after_release():
    logic, log, clock = make()
    logic.key_down()
    logic.combo("v")
    assert "repaste" not in log
    logic.key_up()
    assert log == ["start", "cancel", "repaste"]


def test_combo_ignored_when_key_not_held():
    logic, log, clock = make()
    assert not logic.combo("l")
    assert log == []


def test_auto_repeat_ignored():
    logic, log, clock = make()
    logic.key_down()
    logic.key_down()
    clock.t += 1
    logic.key_up()
    assert log == ["start", "stop"]


# ---------- two-key shortcuts (KeyRouter) ----------

from hushtype.hotkey import VK_L, VK_RALT, VK_SPACE, VK_V, KeyRouter  # noqa: E402

A = 0x41  # the letter A


def router(shortcut="alt_r+space", **kw):
    logic, log, clock = make(**kw)
    return KeyRouter(shortcut, logic), log, clock


def test_combo_hold_both_records_and_release_space_stops():
    r, log, clock = router()
    assert r.event(VK_RALT, True)
    assert r.event(VK_SPACE, True)
    assert log == ["start"]
    clock.t += 2
    assert r.event(VK_SPACE, False)
    assert log == ["start", "stop"]
    assert r.event(VK_RALT, False)
    assert log == ["start", "stop"]


def test_combo_release_alt_first_also_stops_and_space_up_is_swallowed():
    r, log, clock = router()
    r.event(VK_RALT, True); r.event(VK_SPACE, True)
    clock.t += 2
    r.event(VK_RALT, False)
    assert log == ["start", "stop"]
    assert r.event(VK_SPACE, False)  # its down was swallowed, so the up is too
    assert log == ["start", "stop"]


def test_plain_space_and_letters_type_normally():
    r, log, clock = router()
    assert not r.event(VK_SPACE, True)
    assert not r.event(VK_SPACE, False)
    assert not r.event(A, True)
    assert log == []


def test_right_alt_alone_does_nothing_but_is_hidden_from_apps():
    r, log, clock = router()
    assert r.event(VK_RALT, True)
    assert r.event(VK_RALT, False)
    assert log == []


def test_combo_double_tap_space_gives_hands_free():
    r, log, clock = router()
    r.event(VK_RALT, True)
    r.event(VK_SPACE, True); clock.t += 0.1; r.event(VK_SPACE, False)
    clock.t += 0.2
    r.event(VK_SPACE, True); clock.t += 0.1; r.event(VK_SPACE, False)
    r.event(VK_RALT, False)
    assert log[-1] == "hands_free"
    clock.t += 5
    r.event(VK_RALT, True); r.event(VK_SPACE, True)
    assert log[-1] == "stop"


def test_alt_plus_l_switches_language_without_recording():
    r, log, clock = router()
    r.event(VK_RALT, True)
    assert r.event(VK_L, True)
    assert r.event(VK_L, False)
    r.event(VK_RALT, False)
    assert log == ["toggle_language"]


def test_alt_plus_v_repastes_after_alt_release():
    r, log, clock = router()
    r.event(VK_RALT, True)
    r.event(VK_V, True); r.event(VK_V, False)
    assert log == []
    r.event(VK_RALT, False)
    assert log == ["repaste"]


def test_single_key_shortcut_still_works():
    r, log, clock = router("alt_r")
    assert r.event(VK_RALT, True)
    clock.t += 1
    assert r.event(VK_RALT, False)
    assert log == ["start", "stop"]
    assert not r.event(VK_SPACE, True)
