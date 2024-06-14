import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.cell.cell import Cell
from openpyxl.styles import PatternFill
from pathlib import Path


MAX_COLUMNS = 200

COLOR_YELLOW = 'F8F400'
COLOR_LIGHT_YELLOW = 'FAF894'
COLOR_RED = 'FF0000'
COLOR_LIGHT_BLUE = '90DCFE'
COLOR_BLUE = '538DD5'
COLOR_LIGHT_GREEN = 'A4F96B'
COLOR_GREEN = '5AD208'
COLOR_GREY = 'A6A6A6'
COLOR_LIGHT_GREY = 'D9D9D9'


def init(file: str | Path, create_on_error=False) -> Workbook:
    if isinstance(file, str):
        file = Path(file)
    try:
        if file.suffix == '.xlsx':
            return openpyxl.load_workbook(file)
        else:
            from xls2xlsx import XLS2XLSX
            return XLS2XLSX(file).to_xlsx()
    except FileNotFoundError:
        if create_on_error:
            return openpyxl.Workbook()
        else:
            raise FileNotFoundError


def color_cell(cell: Cell, color: str):
    if color:
        cell.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")


def color_row(row: int, color: str, sh: Worksheet):
    for column in range(1, MAX_COLUMNS + 1):
        color_cell(sh.cell(row, column), color)


def find_row(text: str, clmn_number: int, sh: Worksheet) -> int:
    for row in range(2, sh.max_row + 1):
        if str(sh.cell(row, clmn_number).value).lower().strip() == str(text).lower().strip():
            return row


def find_column_by_name(clmn_name: str, sh: Worksheet) -> int:
    for column in range(1, MAX_COLUMNS + 1):
        if sh.cell(1, column).value == clmn_name:
            return column


def clear_row(row: int, sh: Worksheet):
    for column in range(1, MAX_COLUMNS + 1):
        sh.cell(row, column).value = None


def clear_row_from_column(row: int, column: int, sh: Worksheet):
    for column in range(column, MAX_COLUMNS + 1):
        sh.cell(row, column).value = None


def index_file(sh: Worksheet, column: int, strip=True, lower=True) -> dict:
    index = dict()
    for row in range(2, sh.max_row + 1):
        if sh.cell(row, column).value:
            cell_value = str(sh.cell(row, column).value)
            if strip:
                cell_value = cell_value.strip()
            if lower:
                cell_value = cell_value.lower()
            index[cell_value] = row
    return index


def index_file_quick(sh: Worksheet, column: int, strip=True, lower=True) -> dict:
    index = dict()
    for row in range(2, sh.max_row + 1):
        if sh.cell(row, column).value:
            cell_value = str(sh.cell(row, column).value)
            if strip:
                cell_value = cell_value.strip()
            if lower:
                cell_value = cell_value.lower()
            if cell_value not in index:
                index[cell_value] = row
    return index


def get_row(index: dict, value):
    return index.get(str(value).lower().strip())


def add_text_to_column(add_text, column, sh: Worksheet, start_row=2, add_to_empty=True):
    for row in range(start_row, sh.max_row + 1):
        if sh.cell(row, column).value is None or sh.cell(row, column).value == '':
            if not add_to_empty:
                continue
            else:
                cell_text = ''
        else:
            cell_text = str(sh.cell(row, column).value)
        sh.cell(row, column).value = cell_text + add_text


def copy_row(source_row: int, target_row: int, source_sheet: Worksheet, target_sheet: Worksheet=None, move=False):
    if target_sheet is None:
        target_sheet = source_sheet
    for column in range(1, MAX_COLUMNS + 1):
        target_sheet.cell(target_row, column).value = source_sheet.cell(source_row, column).value
        if move:
            clear_row(source_row, source_sheet)


def set_columns_width(width: int, sh: Worksheet) -> None:
    for column_num in range(1, MAX_COLUMNS + 1):
        sh.column_dimensions[get_column_letter(column_num)].width = width
