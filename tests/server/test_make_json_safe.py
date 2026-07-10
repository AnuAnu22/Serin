from __future__ import annotations

from datetime import datetime

from serin.d1_5_ops_tooling.control_panel.server.state import make_json_safe


class TestMakeJsonSafe:
    def test_dict(self) -> None:
        result = make_json_safe({"a": 1, "b": "hello"})
        assert result == {"a": 1, "b": "hello"}

    def test_list(self) -> None:
        result = make_json_safe([1, 2, 3])
        assert result == [1, 2, 3]

    def test_tuple_to_list(self) -> None:
        result = make_json_safe((1, 2))
        assert result == [1, 2]

    def test_set_to_list(self) -> None:
        result = make_json_safe({1, 2, 3})
        assert sorted(result) == [1, 2, 3]

    def test_datetime_to_isoformat(self) -> None:
        dt = datetime(2026, 7, 10, 12, 0, 0)
        result = make_json_safe(dt)
        assert result == "2026-07-10T12:00:00"

    def test_nested_dict(self) -> None:
        data = {"a": {"b": {"c": 1}}}
        result = make_json_safe(data)
        assert result == {"a": {"b": {"c": 1}}}

    def test_nested_with_set(self) -> None:
        data = {"a": {1, 2}, "b": [3, 4]}
        result = make_json_safe(data)
        assert sorted(result["a"]) == [1, 2]
        assert result["b"] == [3, 4]

    def test_custom_object_with_dict(self) -> None:
        class Obj:
            def __init__(self) -> None:
                self.x = 1
                self.y = 2
        result = make_json_safe(Obj())
        assert result == {"x": 1, "y": 2}

    def test_none(self) -> None:
        result = make_json_safe(None)
        assert result is None

    def test_int(self) -> None:
        result = make_json_safe(42)
        assert result == 42

    def test_float(self) -> None:
        result = make_json_safe(3.14)
        assert result == 3.14

    def test_string(self) -> None:
        result = make_json_safe("hello")
        assert result == "hello"

    def test_bool(self) -> None:
        result = make_json_safe(True)
        assert result is True

    def test_mixed_nested(self) -> None:
        data = {
            "name": "test",
            "tags": {"unique", "items"},
            "meta": {"created": datetime(2026, 1, 1, 0, 0, 0)},
            "counts": (1, 2, 3),
        }
        result = make_json_safe(data)
        assert result["name"] == "test"
        assert set(result["tags"]) == {"unique", "items"}
        assert result["meta"]["created"] == "2026-01-01T00:00:00"
        assert result["counts"] == [1, 2, 3]

    def test_empty_dict(self) -> None:
        result = make_json_safe({})
        assert result == {}

    def test_empty_list(self) -> None:
        result = make_json_safe([])
        assert result == []

    def test_empty_set(self) -> None:
        result = make_json_safe(set())
        assert result == []

    def test_custom_object_without_dict(self) -> None:
        class Empty:
            pass
        result = make_json_safe(Empty())
        assert isinstance(result, dict)

    def test_no_circular_reference_handling(self) -> None:
        data: dict = {"a": None}
        data["self"] = data
        import pytest
        with pytest.raises(RecursionError):
            make_json_safe(data)
