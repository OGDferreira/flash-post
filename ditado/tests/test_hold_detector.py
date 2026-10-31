import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ditado import Config, HoldDetector, clean_text  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make():
    events = []
    clock = Clock()
    det = HoldDetector(
        0.25,
        on_arm=lambda: events.append("arm"),
        on_confirm=lambda: events.append("confirm"),
        on_release=lambda: events.append("release"),
        on_cancel=lambda: events.append("cancel"),
        clock=clock,
    )
    return det, events, clock


def test_hold_and_release_dictates():
    det, ev, clock = make()
    det.key_down("ctrl")
    det.key_down("shift")
    clock.t = 0.3
    det.tick()
    det.key_down("shift")  # auto-repeat is ignored
    det.key_up("shift")
    det.key_up("ctrl")
    assert ev == ["arm", "confirm", "release"]


def test_short_tap_is_cancelled():
    det, ev, clock = make()
    det.key_down("shift")
    det.key_down("ctrl")
    clock.t = 0.1
    det.tick()
    det.key_up("ctrl")
    assert ev == ["arm", "cancel"]


def test_ctrl_shift_t_is_not_dictation():
    det, ev, clock = make()
    det.key_down("ctrl")
    det.key_down("shift")
    det.key_down("t")
    clock.t = 1
    det.tick()
    det.key_up("t")
    det.key_up("shift")
    det.key_up("ctrl")
    assert ev == ["arm", "cancel"]


def test_other_key_while_active_cancels():
    det, ev, clock = make()
    det.key_down("ctrl")
    det.key_down("shift")
    clock.t = 0.5
    det.tick()
    det.key_down("s")
    det.key_up("s")
    det.key_up("shift")
    det.key_up("ctrl")
    assert ev == ["arm", "confirm", "cancel"]


def test_typing_capitals_then_ctrl_does_not_arm():
    det, ev, _ = make()
    det.key_down("shift")
    det.key_down("a")
    det.key_up("a")
    det.key_down("ctrl")
    assert ev == []
    det.key_up("ctrl")
    det.key_up("shift")
    det.key_down("ctrl")
    det.key_down("shift")
    assert ev == ["arm"]


def test_works_again_after_use():
    det, ev, clock = make()
    for i in range(2):
        det.key_down("ctrl")
        det.key_down("shift")
        clock.t += 0.3
        det.tick()
        det.key_up("ctrl")
        det.key_up("shift")
    assert ev == ["arm", "confirm", "release"] * 2


def test_stale_key_is_forgotten():
    det, ev, clock = make()
    det.key_down("vk91")  # e.g. Win key whose release got lost on lock screen
    clock.t = 61
    det.tick()
    det.key_down("ctrl")
    det.key_down("shift")
    assert ev == ["arm"]


def test_clean_text():
    cfg = Config()
    assert clean_text("  olá   mundo ", cfg) == "olá mundo "
    assert clean_text("Obrigado.", cfg) == ""
    cfg.trailing_space = False
    assert clean_text("oi", cfg) == "oi"
