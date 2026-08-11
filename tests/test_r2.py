from __future__ import annotations

from pathlib import Path

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from core.r2 import LocalObjectStore, R2Client
from core.settings import Settings


def settings() -> Settings:
    return Settings(
        cm_games=["onepiece"],
        cm_priceguide_url_template="",
        cm_catalogue_url_template="",
        cm_user_agent="tests",
        r2_account_id="",
        r2_access_key_id="",
        r2_secret_access_key="",
        r2_bucket="tcg-raw",
        supabase_db_url="",
        supabase_url="",
        supabase_anon_key="",
        alert_discord_webhook=None,
    )


def test_r2_exists_only_treats_not_found_as_missing() -> None:
    client = boto3.client(
        "s3",
        region_name="auto",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    r2 = R2Client(settings(), client=client)
    with Stubber(client) as stubber:
        stubber.add_client_error(
            "head_object",
            service_error_code="404",
            expected_params={"Bucket": "tcg-raw", "Key": "missing"},
        )
        assert r2.exists("missing") is False

    with Stubber(client) as stubber:
        stubber.add_client_error(
            "head_object",
            service_error_code="AccessDenied",
            expected_params={"Bucket": "tcg-raw", "Key": "denied"},
        )
        with pytest.raises(ClientError):
            r2.exists("denied")


def test_r2_lists_object_metadata_without_downloading_bodies() -> None:
    client = boto3.client(
        "s3",
        region_name="auto",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    r2 = R2Client(settings(), client=client)
    with Stubber(client) as stubber:
        stubber.add_response(
            "list_objects_v2",
            {
                "IsTruncated": False,
                "Name": "tcg-raw",
                "Prefix": "cardmarket/",
                "MaxKeys": 1_000,
                "KeyCount": 1,
                "Contents": [
                    {"Key": "cardmarket/example.json.gz", "Size": 123, "ETag": '"abc"'}
                ],
            },
            {"Bucket": "tcg-raw", "Prefix": "cardmarket/"},
        )
        objects = r2.list_objects("cardmarket/")

    assert objects[0].key == "cardmarket/example.json.gz"
    assert objects[0].size == 123
    assert objects[0].etag == "abc"


def test_local_store_lists_exact_object_sizes(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    store.write_bytes("derived/example.bin", b"12345", "application/octet-stream")
    assert store.list_objects("derived/")[0].size == 5
