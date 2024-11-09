import uuid
import math
from typing import Tuple

from sqlalchemy import select, update, func
from sqlalchemy.exc import NoResultFound

from papermerge.core.exceptions import EntityNotFound
from papermerge.core.db.engine import Session

from papermerge.core import schema
from papermerge.core import orm


def get_tags(
    db_session: Session, *, user_id: uuid.UUID, page_size: int, page_number: int
) -> schema.PaginatedResponse[schema.Tag]:
    stmt_total_tags = select(func.count(orm.Tag.id)).where(orm.Tag.user_id == user_id)
    total_tags = db_session.execute(stmt_total_tags).scalar()

    offset = page_size * (page_number - 1)
    stmt = (
        select(orm.Tag)
        .where(orm.Tag.user_id == user_id)
        .limit(page_size)
        .offset(offset)
    )

    db_tags = db_session.scalars(stmt).all()
    items = [schema.Tag.model_validate(db_tag) for db_tag in db_tags]

    total_pages = math.ceil(total_tags / page_size)

    return schema.PaginatedResponse[schema.Tag](
        items=items, page_size=page_size, page_number=page_number, num_pages=total_pages
    )


def get_tag(
    db_session: Session, tag_id: uuid.UUID, user_id: uuid.UUID
) -> Tuple[schema.Tag | None, schema.Error | None]:

    stmt = select(orm.Tag).where(orm.Tag.user_id == user_id, orm.Tag.id == tag_id)
    try:
        db_item = db_session.scalar(stmt)
    except NoResultFound:
        raise EntityNotFound
    except Exception as e:
        error = schema.Error(messages=[str(e)])
        return None, error

    return schema.Tag.model_validate(db_item), None


def create_tag(
    db_session, attrs: schema.CreateTag, user_id: uuid.UUID
) -> Tuple[schema.Tag | None, schema.Error | None]:

    db_tag = orm.Tag(user_id=user_id, **attrs.model_dump())
    db_session.add(db_tag)

    try:
        db_session.commit()
    except Exception as e:
        error = schema.Error(messages=[str(e)])
        return None, error

    return schema.Tag.model_validate(db_tag), None


def update_tag(
    db_session, tag_id: uuid.UUID, attrs: schema.UpdateTag, user_id: uuid.UUID
) -> Tuple[schema.Tag | None, schema.Error | None]:

    stmt = (
        update(orm.Tag)
        .where(orm.Tag.id == tag_id, orm.Tag.user_id == user_id)
        .values(**attrs.model_dump(exclude_unset=True))
    )
    try:
        db_session.execute(stmt)
        db_session.commit()
        db_tag = db_session.get(orm.Tag, tag_id)
    except Exception as e:
        error = schema.Error(messages=[str(e)])
        return None, error

    return schema.Tag.model_validate(db_tag), None


def delete_tag(
    db_session: Session,
    tag_id: uuid.UUID,
    user_id: uuid.UUID,
):
    stmt = select(orm.Tag).where(orm.Tag.id == tag_id, orm.Tag.user_id == user_id)
    try:
        tag = db_session.execute(stmt, params={"id": tag_id}).scalars().one()
        db_session.delete(tag)
        db_session.commit()
    except NoResultFound:
        raise EntityNotFound()
