from __future__ import annotations

import json
import locale
import logging
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Tuple

import pytest
import yaml

from .conftest import equal_ignore_order

try:
    from kbplacer.kle_serial import (
        Keyboard,
        MatrixAnnotatedKeyboard,
        get_keyboard_from_file,
        parse_ergogen_points,
        parse_kle,
        parse_via,
    )
except Exception:
    pass

logger = logging.getLogger(__name__)


def __minify(string: str) -> str:
    for ch in ["\n", " "]:
        string = string.replace(ch, "")
    return string


# single key layouts with various labels:
@pytest.mark.parametrize(
    # fmt: off
    "layout,expected",
    [
        ([["x"]],                         [          "x"]), # top-left
        ([[{"a":5},"x"]],                 [None,     "x"]), # top-center
        ([["\n\nx"]],                (2 * [None]) + ["x"]), # top-right
        ([[{"a":6},"x"]],            (3 * [None]) + ["x"]), # center-left
        ([[{"a":7},"x"]],            (4 * [None]) + ["x"]), # center
        ([[{"a":6},"\n\nx"]],        (5 * [None]) + ["x"]), # center-right
        ([["\nx"]],                  (6 * [None]) + ["x"]), # bottom-left
        ([[{"a":5},"\nx"]],          (7 * [None]) + ["x"]), # bottom-center
        ([["\n\n\nx"]],              (8 * [None]) + ["x"]), # bottom-right
        ([[{"a":3},"\n\n\n\nx"]],    (9 * [None]) + ["x"]), # front-left
        ([[{"a":7},"\n\n\n\nx"]],   (10 * [None]) + ["x"]), # fron-center
        ([[{"a":3},"\n\n\n\n\nx"]], (11 * [None]) + ["x"]), # front-right
        ([[{"a":0},"x\nx\nx\nx\nx\nx\nx\nx\nx\nx\nx\nx"]], (12 * ["x"])) # all at once
    ],
    # fmt: on
)
def test_labels(layout, expected) -> None:
    result = parse_kle(layout)
    assert result.keys[0].labels == expected
    # check if reverse operation works as well:
    assert [json.loads(result.to_kle())] == layout


class LabelsTestCase(unittest.TestCase):
    def test_too_many_labels(self) -> None:
        labels = "\n".join(13 * ["x"])
        layout = [[{"a": 0}, labels]]
        expected = 12 * ["x"]
        with self.assertLogs("kbplacer.kle_serial", level="INFO") as cm:
            result = parse_kle(layout)
        assert result.keys[0].labels == expected
        self.assertEqual(
            cm.output,
            [
                f"WARNING:kbplacer.kle_serial:Illegal key labels: '{repr(labels)}'. "
                "Labels string can contain 12 '\n' separated items, "
                "ignoring redundant values."
            ],
        )


@pytest.mark.parametrize(
    # fmt: off
    "layout,expected_labels,expected_text_size",
    [
        ([[{"fa":[6]},"x"]],         [          "x"], [               6]),
        ([[{"a":5,"fa":[6]},"x"]],   [     None,"x"], [          None,6]),
        ([[{"fa":[0,0,6]},"\n\nx"]], [None,None,"x"], [     None,None,6]),
        ([[{"f2":6},"\nx"]],    (6 * [None]) + ["x"], (6 * [None]) + [6]),
    ],
    # fmt: on
)
def test_labels_text_size(layout, expected_labels, expected_text_size) -> None:
    result = parse_kle(layout)
    assert result.keys[0].labels == expected_labels
    assert result.keys[0].textSize == expected_text_size
    # check if reverse operation works as well:
    assert [json.loads(result.to_kle())] == layout


def test_labels_colors() -> None:
    # fmt: off
    layout = [[
        {"t": "#ff0000\n\n\n\n\n\n\n\n\n\n#0018ff"},"x\n\n\n\n\n\n\n\n\n\nx",
        {"t": "#ff0000\n\n\n\n\n\n\n\n\n#736827"},"x\n\n\n\n\n\n\n\n\nx",
        {"t": "#210e0e\n\n\n\n\n\n\n\n\n#736827"},"x\n\n\n\n\n\n\n\n\nx\nx",
        {"t": "#000000\n\n\n\n\n\n\n\n\n#a80000"},"x\n\n\n\n\n\n\n\n\nx\nx",
    ]]
    # fmt: on
    result = parse_kle(layout)
    assert [json.loads(result.to_kle())] == layout


def test_float_accuracy() -> None:
    # few first keys from atreus preset
    atreus = (
        '[[{"r":10,"rx":1,"y":-0.1,"x":2},"E"],'
        '[{"y":-0.65,"x":1},"W",{"x":1},"R"],'
        '[{"y":-0.75},"Q"],'
        '[{"y":-0.9,"x":4},"T"],'
        '[{"y":-0.7,"x":2},"D"],'
        '[{"y":-0.65,"x":1},"S",{"x":1},"F"]]'
    )
    layout = json.loads(atreus)
    result = parse_kle(layout)
    positions = [(key.x, key.y) for key in result.keys]
    expected_positions = [
        (3, -0.1),  # E
        (2, 0.25),  # W
        (4, 0.25),  # R
        (1, 0.50),  # Q
        (5, 0.60),  # T
        (3, 0.90),  # D - without rounding in parser this would be
        #                 incorrectly set to (3, 0.9000000000000001)
        #                 accuracy of 6 digit is more than enough and looks cleaner in
        #                 json files
        (2, 1.25),  # S
        (4, 1.25),  # F
    ]
    assert positions == expected_positions


def test_if_produces_valid_json() -> None:
    result = parse_kle([["x"]])
    assert (
        result.to_json() == '{"meta": '
        '{"author": "", "backcolor": "#eeeeee", "background": null, "name": "", '
        '"notes": "", "radii": "", "switchBrand": "", "switchMount": "", "switchType": ""}, '
        '"keys": [{"color": "#cccccc", "labels": ["x"], "textColor": [], "textSize": [], '
        '"default": {"textColor": "#000000", "textSize": 3}, "x": 0, "y": 0, "width": 1, '
        '"height": 1, "x2": 0, "y2": 0, "width2": 1, "height2": 1, "rotation_x": 0, '
        '"rotation_y": 0, "rotation_angle": 0, "decal": false, "ghost": false, "stepped": false, '
        '"nub": false, "profile": "", "sm": "", "sb": "", "st": ""}]}'
    )


def __get_invalid_parse_parameters():
    test_params = []
    test_params.append(pytest.param([], id="empty-list"))
    test_params.append(pytest.param({}, id="empty-dict"))
    test_params.append(pytest.param("", id="empty-string"))
    test_params.append(pytest.param('[["x"]]', id="some-string"))
    test_params.append(pytest.param(["", ""], id="list-of-unexpected-type"))
    test_params.append(pytest.param([{}, {}], id="list-with-wrong-dict-position"))
    test_params.append(pytest.param([[], {}], id="list-with-wrong-dict-position-2"))
    return test_params


@pytest.mark.parametrize("input_object", __get_invalid_parse_parameters())
def test_parse_kle_invalid_schema(input_object) -> None:
    with pytest.raises(RuntimeError):
        parse_kle(input_object)


def test_parse_kle_invalid_key_rotation() -> None:
    with pytest.raises(RuntimeError):
        # Rotation can only be specified on the first key in the row
        layout = [["0", {"r": 15, "rx": 1, "ry": 2}, "1"]]
        parse_kle(layout)


def test_keyboard_from_invalid_type() -> None:
    with pytest.raises(TypeError):
        Keyboard.from_json("{}")  # type: ignore


def test_keyboard_from_invalid_schema() -> None:
    with pytest.raises(KeyError):
        Keyboard.from_json({})  # type: ignore


def get_reference(path: Path):
    with open(path, "r") as f:
        layout: str = f.read()
        reference_dict = json.loads(layout)
        return Keyboard.from_json(reference_dict)


def __get_parameters():
    test_params = []
    # some standard layouts and complex samples from keyboard-layout-editor.com
    kle_presets = [
        "ansi-104-big-ass-enter",
        "ansi-104",
        "apple-wireless",
        "atreus",
        "ergodox",
        "iso-105",
        "kinesis-advantage",
        "symbolics-spacecadet",
    ]
    for f in kle_presets:
        param = pytest.param(
            f"./data/kle-layouts/{f}.json",
            f"./data/kle-layouts/{f}-internal.json",
            id=f,
        )
        test_params.append(param)

    examples = ["2x2", "3x2-sizes", "2x3-rotations", "1x4-rotations-90-step"]
    for e in examples:
        param = pytest.param(
            f"../examples/{e}/kle-annotated.json",
            f"../examples/{e}/kle-internal.json",
            id=e,
        )
        test_params.append(param)

    return test_params


@pytest.mark.parametrize("layout_file,reference_file", __get_parameters())
def test_with_kle_references(layout_file, reference_file, request) -> None:
    test_dir = request.fspath.dirname

    reference = get_reference(Path(test_dir) / reference_file)

    with open(Path(test_dir) / layout_file, "r") as f:
        layout = json.load(f)
        result = parse_kle(layout)
        assert result == reference

        f.seek(0)
        kle_result = json.loads("[" + __minify(result.to_kle()) + "]")
        expected = json.loads(__minify(f.read()))
        assert kle_result == expected


@pytest.mark.parametrize("example", ["2x2", "1x2-with-2U-bottom", "1x1-rotated"])
def test_with_ergogen(example, request) -> None:
    test_dir = request.fspath.dirname

    reference = get_reference(
        Path(test_dir) / f"data/ergogen-layouts/{example}-internal.json"
    )

    # very simple example layout
    with open(Path(test_dir) / f"data/ergogen-layouts/{example}.json", "r") as f:
        layout = json.load(f)
        result = parse_ergogen_points(layout)
        assert result == reference


def _layout_collapse(layout) -> MatrixAnnotatedKeyboard:
    tmp = parse_kle(layout)
    keyboard = MatrixAnnotatedKeyboard(meta=tmp.meta, keys=tmp.keys)
    keyboard.collapse()
    return keyboard


def test_iso_enter_layout_collapse() -> None:
    # fmt: off
    layout =  [
        [{"x":1.25},"1,12",{"w":1.5},"1,13\n\n\n1,0",{"x":1.25,"w":1.25,"h":2,"w2":1.5,"h2":1,"x2":-0.25},"1,13\n\n\n1,1"],
        [{"x":0.5},"2,11",{"w":2.25},"2,12\n\n\n1,0",{"x":0.25},"2,12\n\n\n1,1"],
        ["3,11",{"w":2.75},"3,12\n\n\n3,0",{"x":0.25,"w":1.75},"3,12\n\n\n3,1","3,13\n\n\n3,1"]
    ]
    expected = [
        [{"x":1.25},"1,12",{"w":1.5},"1,13\n\n\n1,0",{"x":-1.25,"w":1.25,"h":2,"w2":1.5,"h2":1,"x2":-0.25},"1,13\n\n\n1,1"],
        [{"x":0.5},"2,11",{"w":2.25},"2,12\n\n\n1,0",{"x":-2.25},"2,12\n\n\n1,1"],
        ["3,11",{"w":2.75},"3,12\n\n\n3,0",{"x":-2.75,"w":1.75},"3,12\n\n\n3,1","3,13\n\n\n3,1"]
    ]
    # fmt: on
    result = _layout_collapse(layout)
    expected_keyboard = parse_kle(expected)
    expected_keyboard = MatrixAnnotatedKeyboard(
        meta=expected_keyboard.meta, keys=expected_keyboard.keys
    )
    assert result == expected_keyboard


def test_bottom_row_collapse_no_extra_keys() -> None:
    # this alternative layout does not introduce any new keys
    # because all are duplicate of original bottom row with the except
    # of two which are missing (and proper alignment forced by decals)
    # fmt: off
    layout = [
        [{"w":1.5},"4,0\n\n\n0,0","4,1\n\n\n0,0",{"w":1.5},"4,2\n\n\n0,0",{"w":7},"4,6\n\n\n0,0",{"w":1.5},"4,10\n\n\n0,0","4,11\n\n\n0,0",{"w":1.5},"4,12\n\n\n0,0"],
        [{"y":0.75,"w":1.5,"d":True},"\n\n\n0,1","4,1\n\n\n0,1",{"w":1.5},"4,2\n\n\n0,1",{"w":7},"4,6\n\n\n0,1",{"w":1.5},"4,10\n\n\n0,1","4,11\n\n\n0,1",{"w":1.5,"d":True},"\n\n\n0,1"]
    ]
    expected = [
        [{"w":1.5},"4,0\n\n\n0,0","4,1\n\n\n0,0",{"w":1.5},"4,2\n\n\n0,0",{"w":7},"4,6\n\n\n0,0",{"w":1.5},"4,10\n\n\n0,0","4,11\n\n\n0,0",{"w":1.5},"4,12\n\n\n0,0"],
    ]
    # fmt: on
    result = _layout_collapse(layout)
    expected_keyboard = parse_kle(expected)
    expected_keyboard = MatrixAnnotatedKeyboard(
        meta=expected_keyboard.meta, keys=expected_keyboard.keys
    )
    assert result == expected_keyboard
    assert len(result.alternative_keys) == 0


def test_bottom_row_decal_handling() -> None:
    # fmt: off
    layout = [
        [{"w":1.5},"4,0\n\n\n0,0","4,1\n\n\n0,0",{"w":1.5},"4,2\n\n\n0,0"],
        [{"y":0.75,"w":1.5,"d":True},"\n\n\n0,1",{"w":2.5},"4,1\n\n\n0,1"]
    ]
    expected = [
        [{"w":1.5},"4,0\n\n\n0,0","4,1\n\n\n0,0",{"x":-1,"w":2.5},"4,1\n\n\n0,1",{"x":-1.5,"w":1.5},"4,2\n\n\n0,0"]
    ]
    # fmt: on
    result = _layout_collapse(layout)
    expected_keyboard = parse_kle(expected)
    expected_keyboard = MatrixAnnotatedKeyboard(
        meta=expected_keyboard.meta, keys=expected_keyboard.keys
    )
    assert result == expected_keyboard
    assert len(result.alternative_keys) == 1


def test_collapse_detects_duplicated_keys() -> None:
    # middle alternative key should be removed because it belongs to the same net,
    # and although it is different size than default choice, the center of a switch
    # is in the same place (so using both would result in overlapping/duplicated
    # footprint)
    # fmt: off
    layout = [
        [{"w":7},"4,6\n\n\n2,0"],
        [{"y":0.5,"w":3},"4,4\n\n\n2,1","4,6\n\n\n2,1",{"w":3},"4,8\n\n\n2,1"]
    ]
    expected = [
        [{"w":7},"4,6\n\n\n2,0",{"x":-7,"w":3},"4,4\n\n\n2,1",{"x":1,"w":3},"4,8\n\n\n2,1"]
    ]
    # fmt: on
    result = _layout_collapse(layout)
    expected_keyboard = parse_kle(expected)
    expected_keyboard = MatrixAnnotatedKeyboard(
        meta=expected_keyboard.meta, keys=expected_keyboard.keys
    )
    assert result == expected_keyboard
    assert len(result.alternative_keys) == 2


@pytest.mark.parametrize("example", ["0_sixty", "wt60_a", "wt60_d"])
def test_with_via_layouts(request, example) -> None:
    test_dir = request.fspath.dirname

    def _reference_keyboard(filename: str) -> MatrixAnnotatedKeyboard:
        reference = get_reference(Path(test_dir) / "data/via-layouts" / filename)
        return MatrixAnnotatedKeyboard(reference.meta, reference.keys)

    with open(Path(test_dir) / f"data/via-layouts/{example}.json", "r") as f:
        layout = json.load(f)
        result = parse_via(layout)
        assert result == _reference_keyboard(f"{example}-internal.json")
        result.collapse()
        reference_collapsed = _reference_keyboard(f"{example}-internal-collapsed.json")
        assert result.keys == reference_collapsed.keys
        # order after collapsing might be different but that's not important right now.
        assert equal_ignore_order(
            result.alternative_keys, reference_collapsed.alternative_keys
        )


class TestKleSerialCli:
    def _run_subprocess(
        self,
        package_path,
        package_name,
        args: dict[str, str] = {},
    ) -> None:
        kbplacer_args = [
            "python3",
            "-m",
            f"{package_name}.kle_serial",
        ]
        for k, v in args.items():
            kbplacer_args.append(k)
            if v:
                kbplacer_args.append(v)

        env = os.environ.copy()
        p = subprocess.Popen(
            kbplacer_args,
            cwd=package_path,
            env=env,
        )
        p.communicate()
        if p.returncode != 0:
            raise Exception("kle_serial __main__ failed")

    @pytest.fixture()
    def example_isolation(self, request, tmpdir, example) -> Tuple[str, str]:
        test_dir = request.fspath.dirname
        source_dir = f"{test_dir}/../examples/{example}"
        shutil.copy(f"{source_dir}/kle-annotated.json", tmpdir)
        shutil.copy(f"{source_dir}/kle-internal.json", tmpdir)
        return f"{tmpdir}/kle-annotated.json", f"{tmpdir}/kle-internal.json"

    @pytest.mark.parametrize(
        "example", ["2x2", "3x2-sizes", "2x3-rotations", "1x4-rotations-90-step"]
    )
    def test_kle_file_convert(
        self, package_path, package_name, example_isolation
    ) -> None:
        raw = example_isolation[0]
        raw_tmp = Path(raw).with_suffix(".json.tmp")
        with open(raw, "r") as f:
            raw_json = json.load(f)

        internal = example_isolation[1]
        internal_tmp = Path(internal).with_suffix(".json.tmp")
        with open(internal, "r") as f:
            internal_json = json.load(f)

        self._run_subprocess(
            package_path,
            package_name,
            {
                "-in": raw,
                "-inform": "KLE_RAW",
                "-out": str(internal_tmp),
                "-outform": "KLE_INTERNAL",
                "-text": "",
            },
        )
        with open(internal_tmp, "r") as f:
            assert json.load(f) == internal_json

        self._run_subprocess(
            package_path,
            package_name,
            {
                "-in": str(internal_tmp),
                "-inform": "KLE_INTERNAL",
                "-out": str(raw_tmp),
                "-outform": "KLE_RAW",
                "-text": "",
            },
        )
        with open(raw_tmp, "r") as f:
            assert json.load(f) == raw_json

    @pytest.mark.parametrize(
        "example,ergogen_filter",
        [
            ("a-dux", ""),
            ("absolem-simple", ""),
            ("corney-island", "^(matrix|thumbfan)"),
        ],
    )
    def test_ergogen_file_convert(
        self, request, tmpdir, package_path, package_name, example, ergogen_filter
    ) -> None:
        test_dir = request.fspath.dirname
        data_dir = f"{test_dir}/data"

        layout_file = f"{tmpdir}/layout.json"
        with open(f"{data_dir}/ergogen-layouts/{example}-points.yaml", "r") as f:
            y = yaml.safe_load(f)
            with open(layout_file, "w") as f2:
                json.dump(y, f2)
        tmp_file = Path(layout_file).with_suffix(".json.tmp")

        args = {
            "-in": layout_file,
            "-inform": "ERGOGEN_INTERNAL",
            "-out": str(tmp_file),
            "-outform": "KLE_RAW",
            "-text": "",
        }
        if ergogen_filter:
            args["-ergogen-filter"] = ergogen_filter
        self._run_subprocess(package_path, package_name, args)

        with open(f"{data_dir}/ergogen-layouts/{example}-reference.json", "r") as f:
            reference = json.load(f)

        with open(tmp_file, "r") as f:
            assert json.load(f) == reference

    def test_ergogen_file_convert_direct_yaml(
        self, request, tmpdir, package_path, package_name
    ) -> None:
        test_dir = request.fspath.dirname
        data_dir = f"{test_dir}/data"
        example = "absolem-simple"
        shutil.copy(f"{data_dir}/ergogen-layouts/{example}-points.yaml", tmpdir)
        layout_file = f"{tmpdir}/{example}-points.yaml"
        tmp_file = Path(layout_file).with_suffix(".json.tmp")
        args = {
            "-in": layout_file,
            "-inform": "ERGOGEN_INTERNAL",
            "-out": str(tmp_file),
            "-outform": "KLE_RAW",
            "-text": "",
        }
        self._run_subprocess(package_path, package_name, args)

        with open(f"{data_dir}/ergogen-layouts/{example}-reference.json", "r") as f:
            reference = json.load(f)

        with open(tmp_file, "r") as f:
            assert json.load(f) == reference


def test_utf8_label(request) -> None:
    test_dir = request.fspath.dirname
    data_dir = f"{test_dir}/data"
    layout_path = f"{data_dir}/kle-layouts/one-key-with-utf-8-label.json"

    logger.info(f"Preferred encoding: {locale.getpreferredencoding()}")
    if sys.version_info >= (3, 11):
        logger.info(f"Encoding: {locale.getencoding()}")

    keyboard = get_keyboard_from_file(layout_path)
    assert len(keyboard.keys) == 1
    assert keyboard.keys[0].labels == ["😊"]
