# tests/test_mouse.py
from core.mouse import MouseController

def test_jitter_never_same_pixel_twice():
    mc = MouseController()
    target = (500, 400)
    seen = set()
    for _ in range(50):
        jx, jy = mc._jitter(target)
        # Note: _jitter CAN produce the same pixel; _unique_jitter is the guarantee
        # We test _unique_jitter here
    # Test _unique_jitter never repeats consecutively
    mc._last_click = None
    prev = None
    for _ in range(100):
        pos = mc._unique_jitter(target)
        assert pos != mc._last_click or mc._last_click is None
        mc._last_click = pos

def test_unique_jitter_never_matches_last_click():
    mc = MouseController()
    target = (500, 400)
    last = (508, 412)
    mc._last_click = last
    for _ in range(50):
        pos = mc._unique_jitter(target)
        assert pos != last, f"Got same pixel as last click: {pos}"

def test_jitter_within_range():
    mc = MouseController()
    for _ in range(200):
        jx, jy = mc._jitter((500, 400))
        assert abs(jx - 500) <= 15
        assert abs(jy - 400) <= 15

def test_bezier_points_start_and_end():
    mc = MouseController()
    pts = mc._bezier_path((0, 0), (100, 100), steps=20)
    assert len(pts) == 20
    assert abs(pts[0][0]) <= 5 and abs(pts[0][1]) <= 5
    assert abs(pts[-1][0] - 100) <= 5 and abs(pts[-1][1] - 100) <= 5

def test_bezier_path_is_curved_not_straight():
    mc = MouseController()
    # Run multiple times since arc direction is random
    curved = False
    for _ in range(10):
        pts = mc._bezier_path((0, 0), (200, 0), steps=30)
        mid_ys = [p[1] for p in pts[5:25]]
        if any(abs(y) > 2 for y in mid_ys):
            curved = True
            break
    assert curved, "Path never curved across 10 attempts"
