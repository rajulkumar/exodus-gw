import mock
import pytest
from fastapi import HTTPException

from exodus_gw import models, routers, schemas


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "env",
    [
        "test",
        "test2",
        "test3",
    ],
)
async def test_publish_env_exists(env, mock_db_session):
    publish = await routers.publish.publish(env=env, db=mock_db_session)
    assert isinstance(publish, models.Publish)


@pytest.mark.asyncio
async def test_publish_env_doesnt_exist(mock_db_session):
    env = "foo"
    with pytest.raises(HTTPException) as exc_info:
        await routers.publish.publish(env=env, db=mock_db_session)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Invalid environment='foo'"


@pytest.mark.asyncio
async def test_publish_links(mock_db_session):
    publish = await routers.publish.publish(env="test", db=mock_db_session)

    # The schema (realistic result) resulting from the publish
    # should contain accurate links.
    assert schemas.Publish(**publish.__dict__).links == {
        "self": "/test/publish/%s" % publish.id,
        "commit": "/test/publish/%s/commit" % publish.id,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "env",
    [
        "test",
        "test2",
        "test3",
    ],
)
async def test_update_publish_items_env_exists(
    env, mock_db_session, mock_item_list
):
    publish_id = "123e4567-e89b-12d3-a456-426614174000"
    # Simulate single item to "test3" environment to test list coercion.
    items = mock_item_list[0] if env == "test3" else mock_item_list

    assert (
        await routers.publish.update_publish_items(
            env=env,
            publish_id=publish_id,
            items=items,
            db=mock_db_session,
        )
        == {}
    )


@pytest.mark.asyncio
async def test_update_publish_items_env_doesnt_exist(
    mock_db_session, mock_item_list
):
    env = "foo"
    publish_id = "123e4567-e89b-12d3-a456-426614174000"

    with pytest.raises(HTTPException) as exc_info:
        await routers.publish.update_publish_items(
            env=env,
            publish_id=publish_id,
            items=mock_item_list,
            db=mock_db_session,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Invalid environment='foo'"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "env",
    [
        "test",
        "test2",
        "test3",
    ],
)
@mock.patch("exodus_gw.routers.publish.write_batches")
@mock.patch("exodus_gw.routers.publish.get_publish_by_id")
async def test_commit_publish(
    mock_get_publish,
    mock_write_batches,
    env,
    mock_publish,
    mock_db_session,
):
    mock_get_publish.return_value = mock_publish
    mock_write_batches.return_value = True

    assert (
        await routers.publish.commit_publish(
            env=env, publish_id=mock_publish.id, db=mock_db_session
        )
        == {}
    )
    # Should write repomd.xml file separately after other items.
    mock_write_batches.assert_has_calls(
        calls=[
            mock.call(env, mock_publish.items[:2]),
            mock.call(env, [mock_publish.items[2]]),
        ],
        any_order=False,
    )


@pytest.mark.asyncio
@mock.patch("exodus_gw.routers.publish.get_publish_by_id")
async def test_commit_publish_env_doesnt_exist(mock_publish, mock_db_session):
    env = "foo"

    with pytest.raises(HTTPException) as exc_info:
        await routers.publish.commit_publish(
            env=env, publish_id=mock_publish.id, db=mock_db_session
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Invalid environment='foo'"


@pytest.mark.asyncio
@mock.patch("exodus_gw.routers.publish.write_batches")
@mock.patch("exodus_gw.routers.publish.get_publish_by_id")
async def test_commit_publish_write_failed(
    mock_get_publish, mock_write_batches, mock_publish, mock_db_session
):
    mock_get_publish.return_value = mock_publish
    mock_write_batches.side_effect = [False, True]

    await routers.publish.commit_publish(
        env="test", publish_id=mock_publish.id, db=mock_db_session
    )

    mock_write_batches.assert_has_calls(
        calls=[
            mock.call("test", mock_publish.items[:2]),
            mock.call("test", mock_publish.items[:2], delete=True),
        ],
        any_order=False,
    )


@pytest.mark.asyncio
@mock.patch("exodus_gw.routers.publish.write_batches")
@mock.patch("exodus_gw.routers.publish.get_publish_by_id")
async def test_commit_publish_entry_point_files_failed(
    mock_get_publish, mock_write_batches, mock_publish, mock_db_session
):
    mock_get_publish.return_value = mock_publish
    mock_write_batches.side_effect = [True, False, True]

    await routers.publish.commit_publish(
        env="test", publish_id=mock_publish.id, db=mock_db_session
    )

    mock_write_batches.assert_has_calls(
        calls=[
            mock.call("test", mock_publish.items[:2]),
            mock.call("test", [mock_publish.items[2]]),
            mock.call("test", mock_publish.items, delete=True),
        ],
        any_order=False,
    )
