def test_node04_failure_sentinel() -> None:
    """Deliberate NODE-04 acceptance failure. This branch must never be merged."""
    assert False, "NODE-04 deliberate failure sentinel"
