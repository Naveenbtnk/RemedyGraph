from parser import gate_parser_entry_points


def test_parser_entry_points_are_gated() -> None:
    assert gate_parser_entry_points() is True
