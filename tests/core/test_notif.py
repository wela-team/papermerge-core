import pytest

from papermerge.core.notif import (
    notification,
    Event,
    State,
    OCREvent
)


@pytest.mark.asyncio
async def test_memory_backend():
    event = Event(
        name='ocr_document_task',
        state=State.started,
        kwargs=OCREvent(
            document_id='abc123',
            user_id='xyz1',
            lang='DEU'
        )
    )
    expected_message = Event(
        name='ocr_document_task',
        state=State.started,
        kwargs=OCREvent(
            document_id='abc123',
            user_id='xyz1',
            lang='DEU'
        )
    )
    await notification.push(event)

    got = await notification.pop()
    assert got == expected_message
