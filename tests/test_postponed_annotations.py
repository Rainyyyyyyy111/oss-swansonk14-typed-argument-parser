from __future__ import annotations

import dataclasses
import sys
from functools import partial
from types import ModuleType
from typing import TYPE_CHECKING, Annotated, ClassVar, List, Optional, Union

import pytest

from tap import Positional, Tap, TapIgnore, tapify, to_tap_class
from tap.tapify import _tap_data_from_data_model

if TYPE_CHECKING:
    Unused = str


@dataclasses.dataclass
class Args:
    arg_int: int = dataclasses.field(metadata={"description": "some integer"})
    arg_bool: bool = True
    arg_list: Optional[List[str]] = None
    hidden: TapIgnore[str] = "hidden"
    unused: ClassVar[Unused]


@pytest.mark.parametrize("target", [Args, Args(0)])
def test_postponed_dataclass_fields(target):
    parser = to_tap_class(target)().parse_args(["--arg_int", "7", "--arg_list", "x", "y"])
    assert parser.as_dict() == {"arg_int": 7, "arg_bool": True, "arg_list": ["x", "y"]}
    assert "some integer" in parser.format_help()
    result = tapify(Args, command_line_args=["--arg_int", "9"], hidden="override")
    assert result == Args(9, hidden="override")


@dataclasses.dataclass
class ScopedArgs:
    Value = int
    value: Annotated[Value, "metadata"]
    label: Positional[str]


def test_postponed_dataclass_metadata_and_class_alias():
    data = _tap_data_from_data_model(ScopedArgs, {})
    assert data.args_data[0].annotation == Annotated[int, "metadata"]
    result = tapify(ScopedArgs, command_line_args=["--value", "42", "label"])
    assert result == ScopedArgs(42, "label")


def test_inherited_annotations_use_defining_scope(monkeypatch):
    module = ModuleType("postponed_base_models")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    exec(
        "from __future__ import annotations\n"
        "from dataclasses import dataclass\n"
        "from typing import Optional\n"
        "Count = int\n"
        "@dataclass\n"
        "class BaseArgs:\n"
        "    Value = int\n"
        "    value: Optional[Value] = None\n"
        "class Driver:\n"
        "    Value = Count\n"
        "    def __init__(self, value: Value):\n"
        "        self.value = value\n",
        module.__dict__,
    )

    @dataclasses.dataclass
    class InheritedArgs(module.BaseArgs):
        Value = str
        label: str = "child"

    class InheritedDriver(module.Driver):
        Value = str

    for target in (InheritedArgs, InheritedDriver, partial(InheritedDriver)):
        result = tapify(target, command_line_args=["--value", "42"])
        assert result.value == 42
        assert to_tap_class(target)().parse_args(["--value", "7"]).value == 7


def test_postponed_bare_optional_and_union():
    class ArgsTap(Tap):
        optional: Optional = None
        union: Union = "default"

        def configure(self):
            self.add_argument("--union", type=int)

    assert ArgsTap().parse_args(["--optional", "text", "--union", "42"]).as_dict() == {
        "optional": "text",
        "union": 42,
    }

    def function(value: Optional = None):
        return value

    assert tapify(function, command_line_args=["--value", "text"]) == "text"


@pytest.mark.parametrize("future_import", [False, True])
def test_explicit_string_converter(future_import):
    namespace = {}
    source = "from __future__ import annotations\n" if future_import else ""
    source += 'def convert(value: "lambda text: int(text) + 1"):\n    return value\n'
    # Explicit flags avoid inheriting this test module's future import in the non-future case.
    exec(compile(source, "<converter>", "exec", dont_inherit=True), namespace)
    assert tapify(namespace["convert"], command_line_args=["--value", "41"]) == 42


def test_postponed_pydantic_dataclass():
    pydantic = pytest.importorskip("pydantic")

    @pydantic.dataclasses.dataclass
    class Config:
        values: Optional[List[str]] = None

    assert tapify(Config, command_line_args=["--values", "x", "y"]).values == ["x", "y"]
    assert to_tap_class(Config)().parse_args([]).values is None


def test_dataclass_with_eager_annotations_and_unregistered_module():
    model = dataclasses.make_dataclass("DynamicArgs", [("value", int)], namespace={"__module__": "missing_module"})
    assert tapify(model, command_line_args=["--value", "42"]).value == 42
