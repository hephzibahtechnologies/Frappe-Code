"""Shared formatting for DMS Excel exports.

Every table cell has a thin border and wrapped text. The header row is bold,
centered, wrapped and bordered, and is sized to fit its wrapped content (never
shorter than 30 points). Numbers and real dates are centered; text -- including
IDs and numeric-looking text such as "007" -- keeps Excel's default left
alignment.

The helpers return the `styles` / `column_widths` arguments that
`frappe.utils.xlsxutils.make_xlsx` already accepts, so an export only has to
build its rows as before and pass these values -- row order, cell values and
cell data types are untouched.

Styles are applied per cell, for the table's own rows and columns only. A
column-wide style would not give blank cells a border in the saved file (Excel
does not store a style for an empty cell) and would also draw borders down the
empty rows below the table.
"""

# Style ids in the registry returned by bordered_styles(). Later ids win when a
# cell has several, so a header cell is [HEADER, *extras] and a body cell is
# [BODY, (CENTER,) *extras].
HEADER_STYLE_ID = 0
BODY_STYLE_ID = 1
CENTER_STYLE_ID = 2

HEADER_FORMAT = {
    "bold": 1,
    "border": 1,
    "align": "center",
    "valign": "vcenter",
    "text_wrap": 1,
}
BODY_FORMAT = {
    "border": 1,
    "valign": "top",
    "text_wrap": 1,
}
# Layered on top of BODY_FORMAT for numbers and real dates only.
CENTER_FORMAT = {"align": "center"}

# Excel column widths, in characters.
MIN_WIDTH = 10
MAX_WIDTH = 45
_PADDING = 2

# Header row height, in points: one line of the 10pt font is about 15.
HEADER_MIN_HEIGHT = 30
_LINE_HEIGHT = 15


def is_centered_value(value):
    """True for the values that are centered: real numbers and real dates.
    Text (even "007"), booleans, None and "" are not."""
    import datetime
    import numbers

    if isinstance(value, bool):
        return False
    return isinstance(value, (datetime.date, datetime.datetime, numbers.Number))


def bordered_styles(column_count, row_count, header_row=0, column_formats=None, rows=None):
    """`styles` for make_xlsx covering every table cell.

    column_count / row_count describe the table (header row included).
    column_formats optionally maps a column index to extra xlsxwriter format
    properties (for example a fill colour) layered on top of the border style
    for that whole column of the table.
    rows, when given, is the list of rows handed to make_xlsx; the body cells
    holding numbers or real dates then also get the centered style.
    """
    styles = [dict(HEADER_FORMAT), dict(BODY_FORMAT), dict(CENTER_FORMAT)]
    extra_ids = {}
    for col, fmt in (column_formats or {}).items():
        styles.append(dict(fmt))
        extra_ids[col] = len(styles) - 1

    cell_styles = {}
    for row in range(row_count):
        base = HEADER_STYLE_ID if row == header_row else BODY_STYLE_ID
        for col in range(column_count):
            ids = [base]
            if rows is not None and row != header_row:
                value = rows[row][col] if row < len(rows) and col < len(rows[row]) else None
                if is_centered_value(value):
                    ids.append(CENTER_STYLE_ID)
            if col in extra_ids:
                ids.append(extra_ids[col])
            cell_styles[(row, col)] = ids

    return {"styles": styles, "cell_styles": cell_styles}


def column_widths(rows):
    """Per-column widths that fit the longest value, within MIN/MAX_WIDTH.

    `rows` is the same list of lists handed to make_xlsx (header first).
    Empty cells are ignored, and long text is capped and left to wrap.
    """
    if not rows:
        return []

    widths = [MIN_WIDTH] * max(len(row) for row in rows)
    for row in rows:
        for col, value in enumerate(row):
            if value is None or value == "":
                continue
            widths[col] = max(widths[col], min(len(str(value)) + _PADDING, MAX_WIDTH))
    return widths


def header_row_height(headers, widths):
    """Height in points that fits every header once it wraps in its column.

    Bold text is wider than the column unit, so two characters are held back
    from each width. Never below HEADER_MIN_HEIGHT.
    """
    import textwrap

    lines = 1
    for text, width in zip(headers, widths):
        if text in (None, ""):
            continue
        wrapped = textwrap.wrap(str(text), width=max(int(width) - 2, 1), break_long_words=True)
        lines = max(lines, len(wrapped))
    return max(HEADER_MIN_HEIGHT, lines * _LINE_HEIGHT)


def make_xlsx_bytes(rows, sheet_name, styles, widths=None):
    """Frappe's make_xlsx (unchanged behaviour: values, cell types and HTML
    handling) plus the one thing make_xlsx cannot do itself -- set the header
    row height. Returns the .xlsx file as bytes."""
    from io import BytesIO

    import xlsxwriter
    from frappe.utils.xlsxutils import get_sanitized_sheet_name, make_xlsx

    widths = widths or column_widths(rows)
    buffer = BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    make_xlsx(rows, sheet_name, wb=workbook, column_widths=widths, styles=styles)
    if rows:
        sheet = workbook.get_worksheet_by_name(get_sanitized_sheet_name(sheet_name))
        sheet.set_row(0, header_row_height(rows[0], widths))
    workbook.close()
    return buffer.getvalue()


def build_workbook(sheet_name, rows, widths=None):
    """A one-sheet workbook (as bytes) with the shared border/header formatting.

    Unlike `make_xlsx`, which writes through xlsxwriter's `write()` and so turns
    any text starting with "=" into a live formula (and "http://..." into a
    hyperlink), every cell here is written with an explicit type:

      * str          -> write_string   (always text, never a formula or link)
      * int / float  -> write_number   (stays numeric, centered)
      * date         -> write_datetime (centered)
      * None / ""    -> bordered blank cell

    so legitimate values are never altered and user-controlled text can never
    execute. `rows` is a list of lists with the header first, like make_xlsx.
    """
    import datetime
    import math
    import numbers
    from io import BytesIO

    import xlsxwriter
    from frappe.utils.xlsxutils import get_sanitized_sheet_name

    buffer = BytesIO()
    workbook = xlsxwriter.Workbook(
        buffer,
        {
            "in_memory": True,
            # belt and braces: write() must never reinterpret text either
            "strings_to_formulas": False,
            "strings_to_urls": False,
            "strings_to_numbers": False,
        },
    )
    header_format = workbook.add_format(HEADER_FORMAT)
    body_format = workbook.add_format(BODY_FORMAT)
    number_format = workbook.add_format({**BODY_FORMAT, **CENTER_FORMAT})
    date_format = workbook.add_format({**BODY_FORMAT, **CENTER_FORMAT, "num_format": "d-mmm-yy"})

    sheet = workbook.add_worksheet(get_sanitized_sheet_name(sheet_name))
    widths = widths or column_widths(rows)
    for col, width in enumerate(widths):
        sheet.set_column(col, col, width)
    if rows:
        sheet.set_row(0, header_row_height(rows[0], widths))

    for row_index, row in enumerate(rows):
        for col, value in enumerate(row):
            if row_index == 0:
                sheet.write_string(row_index, col, "" if value is None else str(value), header_format)
            elif value is None or value == "":
                sheet.write_blank(row_index, col, None, body_format)
            elif isinstance(value, bool):
                sheet.write_boolean(row_index, col, value, body_format)
            elif isinstance(value, (datetime.datetime, datetime.date)):
                sheet.write_datetime(row_index, col, value, date_format)
            elif isinstance(value, numbers.Number):
                number = float(value) if not isinstance(value, int) else value
                if isinstance(number, float) and not math.isfinite(number):
                    sheet.write_string(row_index, col, str(value), body_format)
                else:
                    sheet.write_number(row_index, col, number, number_format)
            else:
                sheet.write_string(row_index, col, str(value), body_format)

    workbook.close()
    return buffer.getvalue()
