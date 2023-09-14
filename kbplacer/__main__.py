import argparse
import json
import logging
from typing import List

import pcbnew

from .defaults import DEFAULT_DIODE_POSITION, ZERO_POSITION
from .element_position import ElementInfo, ElementPosition, Point, PositionOption, Side
from .key_placer import KeyPlacer
from .template_copier import TemplateCopier


class ElementInfoAction(argparse.Action):
    def __call__(self, parser, namespace, values: str, option_string=None) -> None:
        try:
            value: ElementInfo = self.parse(values, option_string)
        except ValueError as e:
            raise argparse.ArgumentTypeError(str(e))
        setattr(namespace, self.dest, value)

    def parse(self, values: str, option_string) -> ElementInfo:
        tokens: list[str] = values.split()
        err = ""
        if len(tokens) not in [2, 6]:
            err = f"{option_string} invalid format."
            raise ValueError(err)
        else:
            annotation = tokens[0]
            if annotation.count("{}") != 1:
                err = (
                    f"'{annotation}' invalid annotation specifier, "
                    "it must contain exactly one '{}' placeholder."
                )
                raise ValueError(err)

            option = PositionOption.get(tokens[1])
            position = None
            if len(tokens) == 2:
                if option not in [
                    PositionOption.CURRENT_RELATIVE,
                    PositionOption.DEFAULT,
                ]:
                    err = (
                        f"{option_string} position option needs to be equal "
                        "CURRENT_RELATIVE or DEFAULT if position details not provided"
                    )
                    raise ValueError(err)
            elif option != PositionOption.CUSTOM:
                err = (
                    f"{option_string} position option needs to be equal CUSTOM "
                    "when providing position details"
                )
                raise ValueError(err)
            else:
                floats = tuple(map(float, tokens[2:5]))
                side = Side.get(tokens[5])
                position = ElementPosition(Point(floats[0], floats[1]), floats[2], side)

            value: ElementInfo = ElementInfo(
                annotation,
                option,
                position,
            )
            return value


class ElementInfoListAction(ElementInfoAction):
    def __call__(self, parser, namespace, values: str, option_string=None) -> None:
        try:
            if "DEFAULT" in values:
                msg = f"{option_string} does not support DEFAULT position"
                raise ValueError(msg)
            value: List[ElementInfo] = []
            tokens: list[str] = values.split(";")
            for token in tokens:
                element_info: ElementInfo = super().parse(token.strip(), option_string)
                value.append(element_info)
        except ValueError as e:
            raise argparse.ArgumentTypeError(str(e))
        setattr(namespace, self.dest, value)


class XYAction(argparse.Action):
    def __call__(self, parser, namespace, values: str, option_string=None) -> None:
        try:
            value = tuple(map(float, values.split()))
            if len(value) != 2:
                msg = (
                    f"{option_string} must be exactly two numeric values "
                    "separated by a space."
                )
                raise ValueError(msg)
        except ValueError as e:
            raise argparse.ArgumentTypeError(str(e))
        setattr(namespace, self.dest, value)


def app():
    parser = argparse.ArgumentParser(
        description="Keyboard's key autoplacer",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "-b", "--board", required=True, help=".kicad_pcb file to be processed"
    )
    parser.add_argument(
        "-l", "--layout", required=False, help="json layout definition file"
    )
    parser.add_argument(
        "-r", "--route", action="store_true", help="Enable experimental routing"
    )
    parser.add_argument(
        "-d",
        "--diode",
        default=ElementInfo("D{}", PositionOption.DEFAULT, DEFAULT_DIODE_POSITION),
        action=ElementInfoAction,
        help=(
            "Diode information, space separated value of ANNOTATION OPTION [POSITION]\n"
            "Available OPTION choices: DEFAULT, CURRENT_RELATIVE and CUSTOM\n"
            "When DEFAULT or CURRENT_RELATIVE, then POSITION needs to be omitted,\n"
            "when CUSTOM, then POSITION is space separated value of X Y ORIENTATION FRONT|BACK\n"
            "for example:\n"
            "\tD{} CURRENT_RELATIVE\n"
            "\tD{} CUSTOM 5 -4.5 90 BACK\n"
            "equal 'D{} DEFAULT' by default"
        ),
    )
    parser.add_argument(
        "--additional-elements",
        default=[
            ElementInfo(
                "ST{}",
                PositionOption.CUSTOM,
                ZERO_POSITION,
            )
        ],
        action=ElementInfoListAction,
        help=(
            "List of ';' separated additional elements ELEMENT_INFO values\n"
            "ELEMENT_INFO is space separated value of ANNOTATION OPTION POSITION\n"
            "Available OPTION choices: CURRENT_RELATIVE and CUSTOM\n"
            "When CURRENT_RELATIVE, then POSITION needs to be omitted,\n"
            "when CUSTOM, then POSITION is space separated value of X Y ORIENTATION FRONT|BACK\n"
            "for example:\n"
            "\tST{} CUSTOM 0 0 180 BACK;LED{} CURRENT_RELATIVE\n"
            "equal 'ST{} CUSTOM 0 0 0 FRONT' by default"
        ),
    )
    parser.add_argument(
        "--key-distance",
        default=(19.05, 19.05),
        action=XYAction,
        help=(
            "X and Y key 1U distance in mm, as two space separated numeric values, "
            "19.05 19.05 by default"
        ),
    )
    parser.add_argument("-t", "--template", help="Controller circuit template")

    args = parser.parse_args()

    layout_path = args.layout
    board_path = args.board
    route_tracks = args.route
    diode = args.diode
    additional_elements = args.additional_elements
    key_distance = args.key_distance
    template_path = args.template

    # set up logger
    logging.basicConfig(
        level=logging.DEBUG, format="%(asctime)s: %(message)s", datefmt="%H:%M:%S"
    )
    logger = logging.getLogger(__name__)

    board = pcbnew.LoadBoard(board_path)

    if layout_path:
        with open(layout_path, "r") as f:
            layout = json.load(f)
    else:
        layout = {}

    placer = KeyPlacer(logger, board, key_distance)
    placer.run(
        layout,
        "SW{}",
        diode,
        route_tracks,
        additional_elements=additional_elements,
    )

    if template_path:
        copier = TemplateCopier(logger, board, template_path, route_tracks)
        copier.run()

    pcbnew.Refresh()
    pcbnew.SaveBoard(board_path, board)

    logging.shutdown()


if __name__ == "__main__":
    app()
