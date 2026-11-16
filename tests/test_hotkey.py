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
