from utils import extract_keyword, clean_ai_response


def test_extract_keyword_from_wiki_tag():
    text = "這是三葉蟲的化石。[[Wiki: Trilobite]]"
    assert extract_keyword(text) == "Trilobite"


def test_extract_keyword_handles_spaces_and_case():
    text = "鑑定結果如下。[[ wiki :  Ammonite  ]]"
    assert extract_keyword(text) == "Ammonite"


def test_extract_keyword_falls_back_to_bold_text():
    text = "這是 **Triceratops** 的化石。"
    assert extract_keyword(text) == "Triceratops"


def test_extract_keyword_returns_none_when_nothing_matches():
    text = "沒有任何標記的一般文字。"
    assert extract_keyword(text) is None


def test_clean_ai_response_strips_wiki_tag():
    text = "這是三葉蟲的化石。[[Wiki: Trilobite]]"
    assert clean_ai_response(text) == "這是三葉蟲的化石。"


def test_clean_ai_response_leaves_normal_text_untouched():
    text = "這段文字完全沒有 wiki 標記。"
    assert clean_ai_response(text) == text
