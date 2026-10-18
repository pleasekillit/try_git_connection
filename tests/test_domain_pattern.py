"""域名表达式匹配与优先级测试。"""
from scripts.config import DomainPattern


def test_exact_match_ignores_case():
    pattern = DomainPattern("github.com")
    assert pattern.is_match("github.com")
    assert pattern.is_match("GitHub.com")
    assert not pattern.is_match("api.github.com")


def test_wildcard_matches_single_label_only():
    pattern = DomainPattern("*.github.com")
    assert pattern.is_match("raw.github.com")
    assert not pattern.is_match("a.b.github.com")
    assert not pattern.is_match("github.com")


def test_wildcard_inside_label():
    pattern = DomainPattern("api-*.github.com")
    assert pattern.is_match("api-x.github.com")
    assert not pattern.is_match("api-x.y.github.com")  # 星号不跨点


def test_ordering_more_specific_first():
    exact = DomainPattern("a.github.com")
    wildcard = DomainPattern("*.github.com")
    assert exact < wildcard


def test_ordering_fewer_segments_first():
    short = DomainPattern("github.com")
    long = DomainPattern("*.github.com")
    assert short < long


def test_sorted_priority():
    patterns = [DomainPattern("*.github.com"), DomainPattern("a.github.com"), DomainPattern("github.com")]
    ordered = [p.pattern for p in sorted(patterns)]
    assert ordered == ["github.com", "a.github.com", "*.github.com"]