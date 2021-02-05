import logging

import mock
import pytest

from exodus_gw.aws import dynamodb


@pytest.mark.parametrize(
    "delete,expected_request",
    [
        (
            False,
            {
                "my-table": [
                    {
                        "PutRequest": {
                            "Item": {
                                "web_uri": {"S": "/some/path"},
                                "object_key": {"S": "abcde"},
                                "from_date": {"S": "2021-01-01T00:00:00.0"},
                            }
                        }
                    },
                    {
                        "PutRequest": {
                            "Item": {
                                "web_uri": {"S": "/other/path"},
                                "object_key": {"S": "a1b2"},
                                "from_date": {"S": "2021-01-01T00:00:00.0"},
                            }
                        }
                    },
                    {
                        "PutRequest": {
                            "Item": {
                                "web_uri": {"S": "/to/repomd.xml"},
                                "object_key": {"S": "c3d4"},
                                "from_date": {"S": "2021-01-01T00:00:00.0"},
                            }
                        }
                    },
                ],
            },
        ),
        (
            True,
            {
                "my-table": [
                    {
                        "DeleteRequest": {
                            "Key": {
                                "web_uri": {"S": "/some/path"},
                                "object_key": {"S": "abcde"},
                                "from_date": {"S": "2021-01-01T00:00:00.0"},
                            }
                        }
                    },
                    {
                        "DeleteRequest": {
                            "Key": {
                                "web_uri": {"S": "/other/path"},
                                "object_key": {"S": "a1b2"},
                                "from_date": {"S": "2021-01-01T00:00:00.0"},
                            }
                        }
                    },
                    {
                        "DeleteRequest": {
                            "Key": {
                                "web_uri": {"S": "/to/repomd.xml"},
                                "object_key": {"S": "c3d4"},
                                "from_date": {"S": "2021-01-01T00:00:00.0"},
                            }
                        }
                    },
                ],
            },
        ),
    ],
    ids=["Put", "Delete"],
)
def test_batch_write(
    mock_boto3_client, mock_publish, delete, expected_request
):
    request = dynamodb.create_request("test", mock_publish.items, delete)

    # Represent successful write/delete of all items to the table.
    mock_boto3_client.batch_write_item.return_value = {"UnprocessedItems": {}}
    dynamodb.batch_write("test", request)

    # Should've requested write of all items.
    mock_boto3_client.batch_write_item.assert_called_once_with(
        RequestItems=expected_request
    )


def test_batch_write_item_limit(mock_boto3_client, mock_publish, caplog):
    items = mock_publish.items * 9
    request = dynamodb.create_request("test", items)

    with pytest.raises(ValueError) as exc_info:
        dynamodb.batch_write("test", request)

    assert "Cannot process more than 25 items per request" in caplog.text
    assert str(exc_info.value) == "Request contains too many items (27)"


@pytest.mark.parametrize("delete", [False, True], ids=["Put", "Delete"])
def test_write_batches(delete, mock_boto3_client, mock_publish, caplog):
    caplog.set_level(logging.INFO, logger="exodus-gw")
    mock_boto3_client.batch_write_item.return_value = {"UnprocessedItems": {}}

    expected_msg = "Items successfully %s" % "deleted" if delete else "written"

    assert dynamodb.write_batches("test", mock_publish.items, delete) is True

    assert expected_msg in caplog.text


@mock.patch("exodus_gw.aws.dynamodb.batch_write")
def test_write_batches_put_fail(mock_batch_write, mock_publish, caplog):
    caplog.set_level(logging.INFO, logger="exodus-gw")
    mock_batch_write.return_value = {
        "UnprocessedItems": {
            "my-table": [
                {"PutRequest": {"Item": mock_publish.items[1].aws_fmt}},
            ]
        }
    }

    assert dynamodb.write_batches("test", mock_publish.items) is False

    assert "One or more writes were unsuccessful" in caplog.text


@mock.patch("exodus_gw.aws.dynamodb.batch_write")
def test_write_batches_delete_fail(mock_batch_write, mock_publish, caplog):
    mock_batch_write.return_value = {
        "UnprocessedItems": {
            "my-table": [
                {"PutRequest": {"Key": mock_publish.items[1].aws_fmt}},
            ]
        }
    }

    with pytest.raises(RuntimeError) as exc_info:
        dynamodb.write_batches("test", mock_publish.items, delete=True)

    assert (
        "Unprocessed items:\n\t%s"
        % str(
            {
                "my-table": [
                    {"PutRequest": {"Key": mock_publish.items[1].aws_fmt}},
                ]
            }
        )
        in caplog.text
    )
    assert "Deletion failed" in str(exc_info.value)


@pytest.mark.parametrize("delete", [False, True], ids=["Put", "Delete"])
def test_write_batches_excs(mock_boto3_client, mock_publish, delete, caplog):
    mock_boto3_client.batch_write_item.side_effect = ValueError()

    expected_msg = "Exception while %s" % "deleting" if delete else "writing"

    with pytest.raises(ValueError):
        dynamodb.write_batches("test", mock_publish.items, delete)

    assert expected_msg in caplog.text
