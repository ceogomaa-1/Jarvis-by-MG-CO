import pytest

from backend.lib.business.creation.standalone_editor import (
    WebsiteEditError,
    apply_exact_operations,
)


def test_exact_operations_change_only_requested_regions():
    html = "<html><body><h1>Old headline</h1><a>Book now</a><footer>Keep me</footer></body></html>"
    updated = apply_exact_operations(
        html,
        [
            {"old": "<h1>Old headline</h1>", "new": "<h1>Fresh food</h1>"},
            {"old": "<a>Book now</a>", "new": '<a class="blue">Book now</a>'},
        ],
    )
    assert "<h1>Fresh food</h1>" in updated
    assert '<a class="blue">Book now</a>' in updated
    assert "<footer>Keep me</footer>" in updated


def test_ambiguous_operation_fails_closed():
    html = "<p>Same</p><p>Same</p>"
    with pytest.raises(WebsiteEditError, match="matched 2 locations"):
        apply_exact_operations(html, [{"old": "<p>Same</p>", "new": "<p>Changed</p>"}])


def test_empty_or_noop_operations_fail_closed():
    with pytest.raises(WebsiteEditError, match="no website changes"):
        apply_exact_operations("<h1>Title</h1>", [])
    with pytest.raises(WebsiteEditError, match="would not change"):
        apply_exact_operations(
            "<h1>Title</h1>",
            [{"old": "<h1>Title</h1>", "new": "<h1>Title</h1>"}],
        )
