import pytest

from src.common.geography import PROVINCES, CCAA, province_code, ccaa_code, provinces_of_ccaa
from src.common.periods import quarter_label, quarter_start


def test_52_provinces_19_ccaa():
    assert len(PROVINCES) == 52
    assert len(CCAA) == 19
    assert sum(len(provinces_of_ccaa(c)) for c in CCAA) == 52


@pytest.mark.parametrize("name,code", [
    ("Álava", "01"), ("Araba/Álava", "01"), ("01 Araba/Álava", "01"), ("Alicante/Alacant", "03"),
    ("Balears, Illes", "07"), ("Islas Baleares", "07"), ("Castellón/Castelló", "12"),
    ("Coruña, A", "15"), ("A Coruña", "15"), ("Gipuzkoa", "20"), ("Guipúzcoa", "20"), ("Jaén", "23"),
    ("León", "24"), ("Lleida", "25"), ("Rioja, La", "26"), ("Comunidad de Madrid", "28"), ("Madrid", "28"),
    ("Palmas, Las", "35"), ("Valencia/València", "46"), ("Bizkaia", "48"), ("Vizcaya", "48"),
    ("Melilla", "52"), ("MÃ¡laga", "29"), ("8", "08"),
])
def test_aliases(name, code):
    assert province_code(name) == code


def test_unknown_raises():
    with pytest.raises(KeyError):
        province_code("Lerida del Norte")
    with pytest.raises(KeyError):
        province_code("08 Madrid")


def test_legacy_names_roundtrip():
    for c, p in PROVINCES.items():
        assert province_code(p.legacy_name) == c
        assert province_code(p.name) == c


def test_ccaa():
    assert ccaa_code("Castilla - La Mancha") == "08"
    assert ccaa_code("16 País Vasco") == "16"
    assert ccaa_code("Balears, Illes") == "04"


def test_periods():
    assert quarter_label("2024-04-01") == "2024Q2"
    assert quarter_label("2024T3") == "2024Q3"
    assert quarter_label("2024 4T") == "2024Q4"
    assert str(quarter_start("2025Q1").date()) == "2025-01-01"
