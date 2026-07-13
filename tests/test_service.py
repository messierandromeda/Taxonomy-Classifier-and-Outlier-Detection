import json
from fastapi.testclient import TestClient

from app.main import app
from app.config import (
    HERBARIUM_ID,
    DB,
    FAMILY,
    FULL_NAME_CACHE,
    NAME_CACHE,
    GENUS,
    COLLECTION_DATE_BEGIN,
    COLLECTION_DATE_END,
    COUNTRY,
    LOCALITY,
    LATITUDE,
    LONGITUDE,
    BARCODE,
    STABLE_URI,
)


client = TestClient(app)

JSON_ENDPOINT = "/detect-json"
CSV_ENDPOINT = "/detect-csv"
TRAIN_ENDPOINT = "/train-csv"


_HEADER_TO_CONST = {
    "HerbariumID": HERBARIUM_ID,
    "DB": DB,
    "Family": FAMILY,
    "FullNameCache": FULL_NAME_CACHE,
    "NameCache": NAME_CACHE,
    "Genus": GENUS,
    "CollectionDateBegin": COLLECTION_DATE_BEGIN,
    "CollectionDateEnd": COLLECTION_DATE_END,
    "Country": COUNTRY,
    "Locality": LOCALITY,
    "Latitude": LATITUDE,
    "Longitude": LONGITUDE,
    "Barcode": BARCODE,
    "StableURI": STABLE_URI,
}


def make_record(**overrides):
    record = {
        HERBARIUM_ID: "test-1",
        DB: "BGBM",
        FAMILY: "Fagaceae",
        FULL_NAME_CACHE: "Quercus robur L.",
        NAME_CACHE: "Quercus robur",
        GENUS: "Quercus",
        COLLECTION_DATE_BEGIN: "2020-05-12",
        COLLECTION_DATE_END: "2020-05-13",
        COUNTRY: "Germany",
        LOCALITY: "Berlin",
        LATITUDE: 52.5,
        LONGITUDE: 13.4,
        BARCODE: "BGBM12345",
        STABLE_URI: "https://example.org/record/test-1",
    }

    converted = {}
    for k, v in overrides.items():
        converted_key = _HEADER_TO_CONST.get(k, k)
        converted[converted_key] = v

    record.update(converted)
    return record


def post_json_file(payload):
    files = {
        "file": (
            "records.json",
            json.dumps(payload),
            "application/json",
        )
    }

    return client.post(
        JSON_ENDPOINT,
        files=files,
    )


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_detect_with_training_subset_size():
    payload = {
        "training_subset_size": 1,
        "records": [make_record(HerbariumID="subset-1")],
    }

    response = post_json_file(payload)

    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_detect_invalid_coordinate():
    payload = {
        "records": [
            make_record(
                HerbariumID="bad-1",
                Latitude=91.2,
            )
        ]
    }

    response = post_json_file(payload)

    assert response.status_code == 200

    flags = response.json()["results"][0]["flags"]

    assert any(flag["type"] == "invalid_coordinate_range" for flag in flags)


def test_detect_invalid_date_order():
    payload = {
        "records": [
            make_record(
                HerbariumID="date-1",
                CollectionDateBegin="2020-05-14",
                CollectionDateEnd="2020-05-13",
            )
        ]
    }

    response = post_json_file(payload)

    assert response.status_code == 200

    flags = response.json()["results"][0]["flags"]

    assert any(flag["type"] == "invalid_date_order" for flag in flags)


def test_detect_invalid_url():
    payload = {
        "records": [
            make_record(
                HerbariumID="url-1",
                StableURI="not-a-valid-url",
            )
        ]
    }

    response = post_json_file(payload)

    assert response.status_code == 200

    flags = response.json()["results"][0]["flags"]

    assert any(flag["type"] == "invalid_url" for flag in flags)


def test_detect_taxonomic_inconsistency():
    payload = {
        "records": [
            make_record(
                HerbariumID="tax-1",
                NameCache="Rosa canina",
                Genus="Quercus",
            )
        ]
    }

    response = post_json_file(payload)

    assert response.status_code == 200

    flags = response.json()["results"][0]["flags"]

    assert any(flag["type"] == "taxonomic_internal_inconsistency" for flag in flags)


def test_detect_json_file_upload():
    payload = {
        "records": [
            make_record(
                HerbariumID="json-upload-1",
                Latitude=999,
            )
        ]
    }

    response = post_json_file(payload)

    assert response.status_code == 200

    data = response.json()

    assert data["count"] == 1
    assert data["annotated_records"][0]["outlier_detected"] is True


def test_annotated_records_contains_confidence():
    payload = {
        "records": [
            make_record(
                HerbariumID="confidence-1",
                Latitude=999,
            )
        ]
    }

    response = post_json_file(payload)

    assert response.status_code == 200

    annotated = response.json()["annotated_records"][0]

    assert annotated["outlier_detected"] is True
    assert annotated["outlier_severity"] == "critical"
    assert annotated["outlier_confidence"] == 100
    assert annotated["outlier_status"] == "confirmed"
    assert annotated["llm_flagged"] is False


def test_detect_csv_download():
    header = ",".join([
        HERBARIUM_ID,
        DB,
        FAMILY,
        FULL_NAME_CACHE,
        NAME_CACHE,
        GENUS,
        COLLECTION_DATE_BEGIN,
        COLLECTION_DATE_END,
        COUNTRY,
        LOCALITY,
        LATITUDE,
        LONGITUDE,
        BARCODE,
        STABLE_URI,
    ])

    csv_content = (
        f"{header}\n"
        "csv-1,BGBM,Fagaceae,Quercus robur L.,Quercus robur,Quercus,"
        "2020-05-12,2020-05-13,Germany,Berlin,"
        "999,13.4,BGBM999,https://example.org/record/csv-1\n"
    )

    files = {
        "file": (
            "records.csv",
            csv_content,
            "text/csv",
        )
    }

    response = client.post(
        f"{CSV_ENDPOINT}?download_csv=true",
        files=files,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "outlier_detected" in response.text
    assert "outlier_confidence" in response.text
    assert "csv-1" in response.text


def test_train_csv_upload():
    header = ",".join([
        HERBARIUM_ID,
        DB,
        FAMILY,
        FULL_NAME_CACHE,
        NAME_CACHE,
        GENUS,
        COLLECTION_DATE_BEGIN,
        COLLECTION_DATE_END,
        COUNTRY,
        LOCALITY,
        LATITUDE,
        LONGITUDE,
        BARCODE,
        STABLE_URI,
    ])

    csv_content = (
        f"{header}\n"
        "train-1,BGBM,Fagaceae,Quercus robur L.,Quercus robur,Quercus,"
        "2020-05-12,2020-05-13,Germany,Berlin,50.0,13.0,BGBMTRAIN,https://example.org/record/train-1\n"
        "train-2,BGBM,Fagaceae,Quercus robur L.,Quercus robur,Quercus,"
        "2020-05-12,2020-05-13,Germany,Berlin,50.1,13.1,BGBMTRAIN2,https://example.org/record/train-2\n"
    )

    files = {
        "file": (
            "train.csv",
            csv_content,
            "text/csv",
        )
    }

    response = client.post(
        TRAIN_ENDPOINT,
        files=files,
        data={"training_subset_size": "2", "training_seed": "42"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Training completed successfully."
    assert payload["trained_records"] == 2
    assert payload["training_subset_size"] == 2
    assert payload["training_seed"] == 42


def test_semantic_detector_species_habitat_contradiction():
    payload = {
        "records": [
            make_record(
                HerbariumID="semantic-1",
                Family="CACTACEAE",
                FullNameCache="Carnegiea gigantea",
                NameCache="Carnegiea gigantea",
                Genus="Carnegiea",
                Locality="feuchter mitteleuropäischer Laubwald",
            )
        ]
    }

    response = post_json_file(payload)

    assert response.status_code == 200

    flags = response.json()["results"][0]["flags"]

    assert any(flag["method"] == "semantic_rule_detector" for flag in flags)


def test_iqr_or_modified_zscore_detector_flags_far_coordinate():
    payload = {
        "records": [
            make_record(HerbariumID="normal-1", Latitude=50.26, Longitude=10.97),
            make_record(HerbariumID="normal-2", Latitude=50.27, Longitude=10.98),
            make_record(HerbariumID="normal-3", Latitude=50.25, Longitude=10.96),
            make_record(HerbariumID="outlier-1", Latitude=23.4, Longitude=30.5),
        ]
    }

    response = post_json_file(payload)

    assert response.status_code == 200

    flags = response.json()["results"][3]["flags"]

    assert any(
        flag["method"]
        in {
            "iqr_detector",
            "modified_zscore_detector",
            "zscore_detector",
        }
        for flag in flags
    )


def test_geo_outlier_is_flagged_by_any_numeric_detector():
    payload = {
        "records": [
            make_record(HerbariumID="normal-1", Latitude=50.26, Longitude=10.97),
            make_record(HerbariumID="normal-2", Latitude=50.27, Longitude=10.98),
            make_record(HerbariumID="normal-3", Latitude=50.25, Longitude=10.96),
            make_record(HerbariumID="normal-4", Latitude=50.28, Longitude=10.99),
            make_record(HerbariumID="normal-5", Latitude=50.24, Longitude=10.95),
            make_record(
                HerbariumID="outlier-geo", Latitude=-33.8688, Longitude=151.2093
            ),
        ],
        "training_subset_size": 6,
    }

    response = post_json_file(payload)

    assert response.status_code == 200

    flags = response.json()["results"][-1]["flags"]

    assert any(
        flag["method"]
        in {
            "iqr_detector",
            "modified_zscore_detector",
            "zscore_detector",
            "isolation_forest_detector",
            "hdbscan_geo_detector",
        }
        for flag in flags
    )


def test_valid_record_endpoint_returns_annotated_result():
    payload = {
        "records": [
            make_record(
                HerbariumID="valid-1",
                Latitude=52.5,
                Longitude=13.4,
            )
        ]
    }

    response = post_json_file(payload)

    assert response.status_code == 200

    data = response.json()

    assert data["count"] == 1
    assert "results" in data
    assert "annotated_records" in data

    annotated = data["annotated_records"][0]

    assert "outlier_detected" in annotated
    assert "outlier_status" in annotated
    assert "outlier_confidence" in annotated
    assert "outlier_severity" in annotated
    assert "outlier_primary_detector" in annotated
    assert "outlier_model_count" in annotated
    assert isinstance(annotated["outlier_model_count"], int)
    assert annotated["outlier_model_count"] >= 0
    assert "llm_flagged" in annotated
    assert annotated["llm_flagged"] is False
    assert "outlier_reason" in annotated
    assert "outlier_summary" in annotated
