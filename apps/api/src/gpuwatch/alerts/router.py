"""Alert rules, events, channels and notification history."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from gpuwatch.alerts import service
from gpuwatch.alerts.schemas import (
    ChannelIn,
    ChannelOut,
    EventOut,
    NotificationOut,
    RuleIn,
    RuleOut,
)
from gpuwatch.auth.dependencies import Admin, Viewer
from gpuwatch.core.deps import ContainerDep, SessionDep
from gpuwatch.core.schemas import Ack

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("/rules", response_model=list[RuleOut], summary="Alert rules")
async def list_rules(_: Viewer, session: SessionDep) -> list[RuleOut]:
    return await service.list_rules(session)


@router.post("/rules", response_model=RuleOut, status_code=201, summary="Add a rule")
async def create_rule(data: RuleIn, actor: Admin, session: SessionDep) -> RuleOut:
    return await service.create_rule(session, data, actor)


@router.put("/rules/{rule_id}", response_model=RuleOut, summary="Edit a rule")
async def update_rule(
    rule_id: uuid.UUID, data: RuleIn, actor: Admin, session: SessionDep
) -> RuleOut:
    return await service.update_rule(session, rule_id, data, actor)


@router.delete("/rules/{rule_id}", response_model=Ack, summary="Delete a rule and its events")
async def delete_rule(rule_id: uuid.UUID, actor: Admin, session: SessionDep) -> Ack:
    await service.delete_rule(session, rule_id, actor)
    return Ack()


@router.get("/events", response_model=list[EventOut], summary="Firing first, then recent")
async def list_events(_: Viewer, session: SessionDep, firing: bool = False) -> list[EventOut]:
    return await service.list_events(session, firing_only=firing)


@router.get("/notifications", response_model=list[NotificationOut], summary="Delivery history")
async def list_notifications(
    _: Viewer, session: SessionDep, event_id: int | None = None
) -> list[NotificationOut]:
    return await service.list_notifications(session, event_id)


@router.get("/channels", response_model=list[ChannelOut], summary="Notification channels")
async def list_channels(actor: Viewer, session: SessionDep) -> list[ChannelOut]:
    return await service.list_channels(session, actor)


@router.post("/channels", response_model=ChannelOut, status_code=201, summary="Add a channel")
async def create_channel(
    data: ChannelIn, actor: Admin, session: SessionDep, container: ContainerDep
) -> ChannelOut:
    return await service.create_channel(session, container, data, actor)


@router.put("/channels/{channel_id}", response_model=ChannelOut, summary="Edit a channel")
async def update_channel(
    channel_id: uuid.UUID,
    data: ChannelIn,
    actor: Admin,
    session: SessionDep,
    container: ContainerDep,
) -> ChannelOut:
    return await service.update_channel(session, container, channel_id, data, actor)


@router.delete("/channels/{channel_id}", response_model=Ack, summary="Delete a channel")
async def delete_channel(channel_id: uuid.UUID, actor: Admin, session: SessionDep) -> Ack:
    await service.delete_channel(session, channel_id, actor)
    return Ack()


@router.post("/channels/{channel_id}/test", response_model=Ack, summary="Send a test notification")
async def test_channel(
    channel_id: uuid.UUID, actor: Admin, session: SessionDep, container: ContainerDep
) -> Ack:
    await service.test_channel(session, channel_id, actor, container.settings.dashboard_url)
    return Ack(message="Test queued; it arrives within a few seconds")
