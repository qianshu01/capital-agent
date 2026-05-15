from ingest.classify import is_family_holder, region_for_country, infer_data_quality

def test_is_family_holder_rejects_corporate_suffixes():
    assert is_family_holder("BlackRock Inc") is False
    assert is_family_holder("Vanguard ETF Trust") is False
    assert is_family_holder("Temasek Holdings Pte Ltd") is False

def test_is_family_holder_accepts_individual_names():
    assert is_family_holder("Li Ka-shing") is True
    assert is_family_holder("Mukesh D. Ambani") is True

def test_is_family_holder_accepts_known_family_dict():
    families = {"HK": ["Li", "Kwok"]}
    assert is_family_holder("Li Family Trust", country="HK", known=families) is True
    assert is_family_holder("Acme Holdings", country="HK", known=families) is False

def test_region_for_country():
    assert region_for_country("HK") == "East Asia"
    assert region_for_country("ID") == "SEA"
    assert region_for_country("IN") == "South Asia"
    assert region_for_country("AU") == "Oceania"
    assert region_for_country("KZ") == "Central Asia"

def test_infer_data_quality():
    # disclosed AUM + controllers + recent activity -> 5
    assert infer_data_quality(aum_basis="disclosed", controllers=["A"], recent_activity_count=1) == 5
    # market cap + controllers + activity -> 4
    assert infer_data_quality(aum_basis="market_cap", controllers=["A"], recent_activity_count=1) == 4
    # estimated, family only -> 2
    assert infer_data_quality(aum_basis="estimate", controllers=None, recent_activity_count=0) == 2
    # nothing -> 1
    assert infer_data_quality(aum_basis=None, controllers=None, recent_activity_count=0) == 1
