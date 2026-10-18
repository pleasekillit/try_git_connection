"""配置加载测试：JSONC 去注释、多文件合并、模型装配、匹配优先级。"""
import json

from scripts.config import load_config, strip_jsonc


def test_strip_jsonc_removes_line_and_block_comments():
    text = '{\n  "a": 1, // 行注释\n  /* 块注释 */ "b": "http://x//y"\n}'
    assert json.loads(strip_jsonc(text)) == {"a": 1, "b": "http://x//y"}


def test_strip_jsonc_keeps_escaped_quote():
    text = '{"a": "he said \\"hi\\" // not a comment"}'
    assert json.loads(strip_jsonc(text))["a"] == 'he said "hi" // not a comment'


def test_load_config_reads_global_options(data_dir):
    config = load_config(data_dir)
    assert config.proxy.port == 38457
    assert config.proxy.listen == "127.0.0.1"
    assert config.dns.doh_servers
    assert config.speed_test.max_ip_count == 3


def test_load_config_merges_group_files(data_dir):
    config = load_config(data_dir)
    assert config.match("github.com") is not None
    assert config.match("registry.npmjs.org") is not None
    assert config.match("fonts.googleapis.com") is not None


def test_match_returns_none_for_unknown(data_dir):
    config = load_config(data_dir)
    assert config.match("example.org") is None


def test_match_prefers_more_specific_rule(data_dir):
    config = load_config(data_dir)
    # api.github.com 的精确规则（tls_sni=false）应优先于 *.github.com
    assert config.match("api.github.com").tls_sni is False
    # 未单列的二级域名落到通配规则
    assert config.match("raw.githubusercontent.com").tls_ignore_name_mismatch is True


def test_load_config_reads_fallback_ip_addresses(data_dir):
    config = load_config(data_dir)
    assert "140.82.112.3" in config.match("github.com").ip_addresses
    assert config.match("example.org") is None


def test_domains_are_sorted(data_dir):
    config = load_config(data_dir)
    patterns = [pattern for pattern, _ in config.domains]
    assert patterns == sorted(patterns)