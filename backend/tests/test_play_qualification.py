from app.api.activity import is_qualified_play


def test_play_qualification_thresholds() -> None:
    assert is_qualified_play(30, 200)
    assert is_qualified_play(8, 10)
    assert not is_qualified_play(7, 10)
    assert not is_qualified_play(29, 60)
    assert not is_qualified_play(0, 5)
    assert not is_qualified_play(10, 0)
