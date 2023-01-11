from typing import List

# ASCII escape sequences
# adopted from my personal terminal.h header file for C

ESC = '\033'
# CSI (Control Sequence Introducer) sequences
# see https:#en.wikipedia.org/wiki/ANSI_escape_code#CSI_sequences
CSI = f'{ESC}['
CSI_SHOW_CURSOR = f'{CSI}?25h'
CSI_HIDE_CURSOR = f'{CSI}?25l'


def csi_cursor_position(line: int, col: int):
    return f'{CSI}{line};{col}H'


def csi_erase_in_display(n: int):
    return f'{CSI}{n}J'


def csi_erase_in_line(n: int):
    return f'{CSI}{n}K'


# SGR (Select Graphic Rendition) parameters
# see https:#en.wikipedia.org/wiki/ANSI_escape_code#SGR_(Select_Graphic_Rendition)_parameters
# multiple arguments can be specified at once, must be separated by semicolon (;)
def csi_sgr(attrs: List[str]):
    attrs_str = ';'.join(attrs)
    return f'{CSI}{attrs_str}m'


rst = f'{CSI}0m'

bold = '1'
underline = '4'

# SGR colors
# see https:#en.wikipedia.org/wiki/ANSI_escape_code#Colors
#
#     SGR    description                    notes
#   30–37    Set foreground color
#      38    Set foreground color           Next arguments are 5;n or 2;r;g;b
#      39    Default foreground color       Implementation defined (according to standard)
#   40–47    Set background color
#      48    Set background color           Next arguments are 5;n or 2;r;g;b
#      49    Default background color       Implementation defined (according to standard)
#   90–97    Set bright foreground color    Not in standard
# 100–107    Set bright background color    Not in standard

# 0-7 3-bit colors
# 0 Black
# 1 Red
# 2 Green
# 3 Yellow
# 4 Blue
# 5 Magenta
# 6 Cyan
# 7 White

fg_black = '30'
fg_red = '31'
fg_green = '32'
fg_yellow = '33'
fg_blue = '34'
fg_magenta = '35'
fg_cyan = '36'
fg_white = '37'

bg_black = '40'
bg_red = '41'
bg_green = '42'
bg_yellow = '43'
bg_blue = '44'
bg_magenta = '45'
bg_cyan = '46'
bg_white = '47'

fg_bright_black = '90'
fg_bright_red = '91'
fg_bright_green = '92'
fg_bright_yellow = '93'
fg_bright_blue = '94'
fg_bright_magenta = '95'
fg_bright_cyan = '96'
fg_bright_white = '97'

bg_bright_black = '100'
bg_bright_red = '101'
bg_bright_green = '102'
bg_bright_yellow = '103'
bg_bright_blue = '104'
bg_bright_magenta = '105'
bg_bright_cyan = '106'
bg_bright_white = '107'

# simplified usage

red = csi_sgr([fg_red, bold])
green = csi_sgr([fg_green, bold])
yellow = csi_sgr([fg_bright_yellow, bold])
blue = csi_sgr([fg_blue, bold])
magenta = csi_sgr([fg_magenta, bold])
cyan = csi_sgr([fg_cyan, bold])
gray = csi_sgr([fg_bright_black])
gray_bold = csi_sgr([fg_bright_black, bold])

# def red(text: str):
#     return f'{csi_sgr([fg_red, bold])}{text}{rst}'
#
#
# def green(text: str):
#     return f'{csi_sgr([fg_green, bold])}{text}{rst}'
#
#
# def yellow(text: str):
#     return f'{csi_sgr([fg_bright_yellow, bold])}{text}{rst}'
#
#
# def blue(text: str):
#     return f'{csi_sgr([fg_blue, bold])}{text}{rst}'
#
#
# def magenta(text: str):
#     return f'{csi_sgr([fg_magenta, bold])}{text}{rst}'
#
#
# def cyan(text: str):
#     return f'{csi_sgr([fg_cyan, bold])}{text}{rst}'
#
#
# def gray(text: str):
#     return f'{csi_sgr([fg_bright_black])}{text}{rst}'
#
#
# def gray_bold(text: str):
#     return f'{csi_sgr([fg_bright_black, bold])}{text}{rst}'
