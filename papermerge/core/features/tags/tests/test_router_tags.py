from sqlalchemy import func

from papermerge.core.db.engine import Session
from papermerge.core import orm, schema
from papermerge.test.types import AuthTestClient


def test_create_tag_route(auth_api_client: AuthTestClient, db_session: Session):
    count_before = db_session.query(func.count(orm.Tag.id)).scalar()
    assert count_before == 0

    response = auth_api_client.post(
        "/tags/",
        json={"name": "important"},
    )

    assert response.status_code == 201, response.json()
    count_after = db_session.query(func.count(orm.Tag.id)).scalar()
    assert count_after == 1


def test_update_tag_route(auth_api_client: AuthTestClient, make_tag, user):
    tag: schema.Tag = make_tag(name="draft", bg_color="red", user=user)

    response = auth_api_client.patch(
        f"/tags/{tag.id}",
        # only `name` attr is being updated
        json={"name": "draft-updated"},
    )

    assert response.status_code == 200, response.json()
    with Session() as s:
        updated_tag = s.get(orm.Tag, tag.id)

    # `name` attribute was updated
    assert updated_tag.name == "draft-updated"
    # other attributes did not change
    assert updated_tag.bg_color == tag.bg_color
    assert updated_tag.fg_color == tag.fg_color


def test_get_tag_route(auth_api_client: AuthTestClient, make_tag, user):
    tag: schema.Tag = make_tag(name="draft", bg_color="red", user=user)

    response = auth_api_client.get(
        f"/tags/{tag.id}",
    )

    assert response.status_code == 200, response.json()


def test_delete_tag_route(auth_api_client: AuthTestClient, db_session, make_tag, user):
    tag: schema.Tag = make_tag(name="draft", bg_color="red", user=user)

    response = auth_api_client.delete(
        f"/tags/{tag.id}",
    )

    assert response.status_code == 204
    tags_count = db_session.query(func.count(orm.Tag.id)).scalar()
    assert tags_count == 0


def test_tags_paginated_result__8_items_first_page(
    make_tag, auth_api_client: AuthTestClient, user
):
    total_tags = 8
    for i in range(total_tags):
        make_tag(name=f"Tag {i}", user=user)

    params = {"page_size": 5, "page_number": 1}
    response = auth_api_client.get("/tags/", params=params)

    assert response.status_code == 200, response.json()

    paginated_items = schema.PaginatedResponse[schema.Tag](**response.json())

    assert paginated_items.page_size == 5
    assert paginated_items.page_number == 1
    assert paginated_items.num_pages == 2
    assert len(paginated_items.items) == 5
