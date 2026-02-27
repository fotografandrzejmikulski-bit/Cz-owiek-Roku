"""
Modele danych dla komunikacji między agentami i klientami.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class MessageType(str, Enum):
    """Typy wiadomości w systemie wieloagentowym."""
    TASK_REQUEST = "task_request"
    TASK_RESULT = "task_result"
    AGENT_STATUS = "agent_status"
    BROADCAST = "broadcast"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


class AgentStatus(str, Enum):
    """Statusy agentów w systemie."""
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    ERROR = "error"
    OFFLINE = "offline"


@dataclass
class AgentMessage:
    """Wiadomość wymieniana między agentami (protokół MAS)."""
    type: MessageType
    sender_id: str
    payload: dict[str, Any]
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    receiver_id: str | None = None
    correlation_id: str | None = None
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    priority: int = 0  # 0 = normalna, wyższe = ważniejsze

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "type": self.type.value,
            "sender_id": self.sender_id,
            "receiver_id": self.receiver_id,
            "correlation_id": self.correlation_id,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentMessage":
        return cls(
            message_id=data["message_id"],
            type=MessageType(data["type"]),
            sender_id=data["sender_id"],
            receiver_id=data.get("receiver_id"),
            correlation_id=data.get("correlation_id"),
            payload=data["payload"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            priority=data.get("priority", 0),
        )
