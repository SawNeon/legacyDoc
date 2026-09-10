"""Cross-file symbol index tests."""

from __future__ import annotations

from legacydoc_parsing import detect_language, parse_file
from legacydoc_parsing.symbol_index import SymbolIndex, render_external_symbols

ORDERS_MODULE = """\
def validate_order(order, stock):
    if order.quantity > stock:
        raise ValueError("insufficient stock")
    return True


def calculate_shipping(postal_code, weight_kg):
    return weight_kg * 2.5
"""

CHECKOUT_MODULE = """\
def finish_purchase(order, stock, postal_code):
    validate_order(order, stock)
    shipping = calculate_shipping(postal_code, order.weight_kg)
    return shipping
"""

NOTIFICATION_MODULE = """\
def send_email(recipient, subject):
    return True
"""


def build_index(*files: tuple[str, str]) -> SymbolIndex:
    index = SymbolIndex()

    for path, source in files:
        language = detect_language(path)
        assert language is not None
        index.add_file(parse_file(path, source, language))

    return index


def test_indexes_symbols_from_multiple_files():
    index = build_index(("orders.py", ORDERS_MODULE), ("checkout.py", CHECKOUT_MODULE))

    assert index.file_count == 2
    assert index.symbol_count == 3


def test_returns_only_referenced_symbols():
    index = build_index(
        ("orders.py", ORDERS_MODULE),
        ("checkout.py", CHECKOUT_MODULE),
        ("notification.py", NOTIFICATION_MODULE),
    )

    references = index.references_in(CHECKOUT_MODULE, exclude_path="checkout.py")

    assert {symbol.name for symbol in references} == {"validate_order", "calculate_shipping"}


def test_excludes_symbols_from_the_same_file():
    index = build_index(("orders.py", ORDERS_MODULE), ("checkout.py", CHECKOUT_MODULE))

    references = index.references_in(ORDERS_MODULE, exclude_path="orders.py")

    assert all(symbol.path != "orders.py" for symbol in references)


def test_orders_by_mention_frequency():
    index = build_index(("orders.py", ORDERS_MODULE), ("other.py", "x = 1\n"))

    source = "validate_order(a)\nvalidate_order(b)\nvalidate_order(c)\ncalculate_shipping(d)\n"
    references = index.references_in(source, exclude_path="usage.py")

    assert references[0].name == "validate_order"


def test_respects_character_budget():
    files = [
        (f"module_{i}.py", f"def very_long_function_name_{i}(first, second):\n    return 1\n")
        for i in range(40)
    ]
    index = build_index(*files)

    source = "\n".join(f"very_long_function_name_{i}()" for i in range(40))
    references = index.references_in(source, exclude_path="usage.py", max_chars=300)

    assert len(render_external_symbols(references)) <= 400
    assert references


def test_respects_symbol_limit():
    files = [
        (f"m{i}.py", f"def function_number_{i}(value):\n    return value\n") for i in range(30)
    ]
    index = build_index(*files)

    source = "\n".join(f"function_number_{i}()" for i in range(30))
    references = index.references_in(source, exclude_path="usage.py", max_symbols=5)

    assert len(references) == 5


def test_ignores_common_identifiers():
    index = build_index(("util.py", "def get(x):\n    return x\n\ndef data(y):\n    return y\n"))

    assert index.references_in("get(1)\ndata(2)\n", exclude_path="usage.py") == []


def test_summary_is_attached_after_file_is_documented():
    index = build_index(("orders.py", ORDERS_MODULE))

    before = index.references_in(CHECKOUT_MODULE, exclude_path="checkout.py")
    assert all(symbol.summary is None for symbol in before)

    index.attach_summaries("orders.py", {"validate_order": "Rejects orders above stock."})

    after = index.references_in(CHECKOUT_MODULE, exclude_path="checkout.py")
    validate = next(symbol for symbol in after if symbol.name == "validate_order")

    assert validate.summary == "Rejects orders above stock."
    assert "Rejects orders" in render_external_symbols(after)


def test_render_includes_source_file():
    index = build_index(("orders.py", ORDERS_MODULE))

    rendered = render_external_symbols(
        index.references_in(CHECKOUT_MODULE, exclude_path="checkout.py")
    )

    assert "orders.py" in rendered
    assert "validate_order" in rendered


def test_empty_index_returns_no_references():
    assert SymbolIndex().references_in("anything", exclude_path="a.py") == []


def test_works_across_languages():
    index = build_index(
        ("service.go", "func ProcessPayment(amount int) error {\n    return nil\n}\n"),
        ("handler.py", "def invoke():\n    return 1\n"),
    )

    references = index.references_in("ProcessPayment(100)", exclude_path="handler.py")

    assert [symbol.name for symbol in references] == ["ProcessPayment"]
    assert references[0].path == "service.go"
