import pytest

from slideshow_maker.timeline import build_timeline, per_image_seconds


def test_build_timeline_overlaps_by_transition():
    tl = build_timeline([3.0, 3.0, 3.0], 0.5)
    assert tl.total == pytest.approx(8.0)
    assert [s.start for s in tl.slots] == pytest.approx([0.0, 2.5, 5.0])


def test_single_slot_has_no_transition():
    tl = build_timeline([4.0], 1.0)
    assert tl.transition == 0.0 and tl.total == 4.0
    st = tl.state_at(3.9)
    assert st.current == 0 and st.incoming is None


def test_state_at_inside_and_during_transition():
    tl = build_timeline([2.0, 2.0], 0.5)
    st = tl.state_at(1.0)
    assert st.current == 0 and st.incoming is None and st.progress == pytest.approx(0.5)
    st = tl.state_at(1.75)                   # halfway through the 1.5 .. 2.0 overlap
    assert st.current == 0 and st.incoming == 1
    assert st.blend == pytest.approx(0.5)
    assert st.incoming_progress == pytest.approx(0.125)
    st = tl.state_at(2.5)
    assert st.current == 1 and st.incoming is None


def test_state_at_clamps_out_of_range():
    tl = build_timeline([1.0, 1.0], 0.0)
    assert tl.state_at(-5).current == 0
    assert tl.state_at(99).current == 1


def test_per_image_seconds_solves_total():
    # 4 images, 0.5 s transitions, 2 s end card, total 12 s
    per = per_image_seconds(4, 3.0, 12.0, 0.5, 2.0, True)
    durations = [per] * 4 + [2.0]
    assert build_timeline(durations, 0.5).total == pytest.approx(12.0)


def test_per_image_seconds_without_total():
    assert per_image_seconds(3, 2.5, 0.0, 0.5) == 2.5
    # never shorter than the transition
    assert per_image_seconds(3, 0.2, 0.0, 0.5) == pytest.approx(0.55)
    assert per_image_seconds(0, 2.5, 0.0, 0.5) == 0.0
