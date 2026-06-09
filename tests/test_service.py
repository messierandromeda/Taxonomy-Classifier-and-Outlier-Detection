from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    # Health endpoint should return ok status.
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_detect_with_training_subset_size():
    payload = {
        "training_subset_size": 1,
        "records": [
            {
                "HerbariumID": "subset-1",
                "DB": "BGBM",
                "Family": "Fagaceae",
                "FullNameCache": "Quercus robur L.",
                "NameCache": "Quercus robur",
                "Genus": "Quercus",
                "CollectionDateBegin": "2020-05-12",
                "CollectionDateEnd": "2020-05-13",
                "Country": "Germany",
                "Locality": "Berlin",
                "Latitude": 52.5,
                "Longitude": 13.4,
                "Barcode": "BGBM12349",
                "StableURI": "https://example.org/record/subset-1",
            }
        ]
    }

    response = client.post("/detect", json=payload)

    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_detect_invalid_coordinate():
    # Latitude above 90 must be flagged.
    payload = {
        "records": [
            {
                "HerbariumID": "bad-1",
                "DB": "BGBM",
                "Family": "Fagaceae",
                "FullNameCache": "Quercus robur L.",
                "NameCache": "Quercus robur",
                "Genus": "Quercus",
                "CollectionDateBegin": "2020-05-12",
                "CollectionDateEnd": "2020-05-13",
                "Country": "Germany",
                "Locality": "Berlin",
                "Latitude": 91.2,
                "Longitude": 13.4,
                "Barcode": "BGBM12345",
                "StableURI": "https://example.org/record/bad-1",
            }
        ]
    }

    response = client.post("/detect", json=payload)

    assert response.status_code == 200

    data = response.json()

    assert data["count"] == 1

    flags = data["results"][0]["flags"]

    assert any(
        flag["type"] == "invalid_coordinate_range"
        for flag in flags
    )


def test_detect_invalid_date_order():
    # Begin date after end date must be flagged.
    payload = {
        "records": [
            {
                "HerbariumID": "date-1",
                "DB": "BGBM",
                "Family": "Fagaceae",
                "FullNameCache": "Quercus robur L.",
                "NameCache": "Quercus robur",
                "Genus": "Quercus",
                "CollectionDateBegin": "2020-05-14",
                "CollectionDateEnd": "2020-05-13",
                "Country": "Germany",
                "Locality": "Berlin",
                "Latitude": 52.5,
                "Longitude": 13.4,
                "Barcode": "BGBM12346",
                "StableURI": "https://example.org/record/date-1",
            }
        ]
    }

    response = client.post("/detect", json=payload)

    assert response.status_code == 200

    flags = response.json()["results"][0]["flags"]

    assert any(
        flag["type"] == "invalid_date_order"
        for flag in flags
    )


def test_detect_invalid_url():
    # StableURI must be a valid http/https URL.
    payload = {
        "records": [
            {
                "HerbariumID": "url-1",
                "DB": "BGBM",
                "Family": "Fagaceae",
                "FullNameCache": "Quercus robur L.",
                "NameCache": "Quercus robur",
                "Genus": "Quercus",
                "CollectionDateBegin": "2020-05-12",
                "CollectionDateEnd": "2020-05-13",
                "Country": "Germany",
                "Locality": "Berlin",
                "Latitude": 52.5,
                "Longitude": 13.4,
                "Barcode": "BGBM12347",
                "StableURI": "not-a-valid-url",
            }
        ]
    }

    response = client.post("/detect", json=payload)

    assert response.status_code == 200

    flags = response.json()["results"][0]["flags"]

    assert any(
        flag["type"] == "invalid_url"
        for flag in flags
    )


def test_detect_taxonomic_inconsistency():
    # Genus must match the beginning of scientificName.
    payload = {
        "records": [
            {
                "HerbariumID": "tax-1",
                "DB": "BGBM",
                "Family": "Fagaceae",
                "FullNameCache": "Quercus robur L.",
                "NameCache": "Rosa canina",
                "Genus": "Quercus",
                "CollectionDateBegin": "2020-05-12",
                "CollectionDateEnd": "2020-05-13",
                "Country": "Germany",
                "Locality": "Berlin",
                "Latitude": 52.5,
                "Longitude": 13.4,
                "Barcode": "BGBM12348",
                "StableURI": "https://example.org/record/tax-1",
            }
        ]
    }

    response = client.post("/detect", json=payload)

    assert response.status_code == 200

    flags = response.json()["results"][0]["flags"]

    assert any(
        flag["type"] == "taxonomic_internal_inconsistency"
        for flag in flags
    )