def test_node04_failure_sentinel() -> None:
    """Deliberate NODE-04 acceptance failure. This branch must never be merged."""
    expected = 1
    actual = 2
    assert actual == expected
