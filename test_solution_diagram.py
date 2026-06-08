import os
import pytest
from html.parser import HTMLParser


DIAGRAM_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "solution_diagram.html")


class TableHeaderChecker(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.table_count = 0
        self.tables_with_th = set()
        self.current_table = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.current_table += 1
            self.table_count += 1
            self.in_table = True
        elif tag == "th" and self.in_table:
            self.tables_with_th.add(self.current_table)

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False


def test_solution_diagram_file_exists():
    assert os.path.isfile(DIAGRAM_PATH), f"File not found: {DIAGRAM_PATH}"


def test_all_tables_have_th_headers():
    """Fix scenario: every <table> in solution_diagram.html must contain <th> elements."""
    with open(DIAGRAM_PATH, encoding="utf-8") as f:
        content = f.read()

    checker = TableHeaderChecker()
    checker.feed(content)

    assert checker.table_count > 0, "No <table> elements found in file"
    tables_without_headers = set(range(1, checker.table_count + 1)) - checker.tables_with_th
    assert not tables_without_headers, (
        f"Tables {sorted(tables_without_headers)} have no <th> headers"
    )
