from scripts.content_collector import match_industries


def test_match_industries_is_case_insensitive_and_deduplicated():
    industries = [{"name": "人工智能", "keywords": ["AI", "大模型", "ai"]}]

    assert match_industries("AI 大模型加速发展", industries) == ["人工智能"]
