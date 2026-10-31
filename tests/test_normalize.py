from ppu.normalize import (
    clean_text,
    core_name,
    expand_abbreviations,
    extract_entities,
    normalize_record,
)


def test_placeholders_become_empty():
    for s in ["См.вложение", "См.вложение ", "см. приложение", "См. во вложении", "-", None]:
        assert clean_text(s) == ""


def test_placeholder_inside_text_is_removed():
    assert clean_text("Шум на участке. См.вложение") == "Шум на участке."


def test_html_lists_are_flattened():
    s = "Уменьшение шума. </li><li>Рост качества."
    assert clean_text(s) == "Уменьшение шума. Рост качества."


def test_abbreviations():
    assert expand_abbreviations("Орг. эл. учета мест хранения") == \
        "организация электронного учета мест хранения"
    assert expand_abbreviations("Улучшение культуры пр-ва пов-ие пр-ти труда") == \
        "Улучшение культуры производства повышение производительности труда"
    assert expand_abbreviations("принтера на уч 7500") == "принтера на участок 7500"
    assert expand_abbreviations("Согласование РКД пр.24800") == \
        "Согласование РКД (рабочая конструкторская документация) проект 24800"


def test_short_words_are_not_mistaken_for_abbreviations():
    # «пр.» без номера и слова, начинающиеся с «уч», не трогаем
    assert expand_abbreviations("учет и пр. вопросы") == "учет и пр. вопросы"


def test_entities():
    text = expand_abbreviations(
        "шум на участке №19 цеха 14016 от виброустановки мод. SCV-400 инв. №020009"
    )
    assert extract_entities(text) == {
        "workshops": ["14016"],
        "sites": ["19"],
        "models": ["SCV-400"],
        "inventory": ["020009"],
    }


def test_named_place_only_from_name():
    r = normalize_record({"name": "Улучшение культуры пр-ва. Участок люм-контроля.",
                          "before": "Шум на метизном участке участка №19", "after": None,
                          "proposal": None, "result": None})
    assert r["entities"] == {"sites": ["19"], "places": ["участок люм-контроля"]}


def test_core_name_drops_location_and_dates():
    def core(s):
        return core_name(expand_abbreviations(s))

    assert core("Улучшение культуры пр-ва. Цех 26") == "Улучшение культуры производства"
    assert core("Улучшение культуры пр-ва. Цех 29( МП)") == \
        core("Улучшение культуры пр-ва. Участок люм-контроля.")
    assert core("14.08.2018 Согласование РКД пр.24800") == \
        core("Согласование РКД пр. 24040")
    assert core("Внедрение принтера на уч 7500") == "Внедрение принтера"


def test_completeness():
    base = {"name": "Ручки для напильников", "result": None}
    full = normalize_record({**base, "before": "a", "after": "b", "proposal": "c"})
    name_only = normalize_record(
        {**base, "before": "См.вложение", "after": "См.вложение", "proposal": "См.вложение"}
    )
    partial = normalize_record({**base, "before": "a", "after": None, "proposal": "-"})
    assert (full["completeness"], partial["completeness"], name_only["completeness"]) == \
        ("full", "partial", "name_only")
