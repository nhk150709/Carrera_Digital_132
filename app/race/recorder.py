"""Records a player's control input over time (throttle, brake, lane change,
lap crossings, race-stop events) so a session can be replayed later --
primarily to drive the custom pace car as a "ghost" of a real lap.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path


class EventType(str, Enum):
    THROTTLE = "throttle"
    BRAKE = "brake"
    LANE_CHANGE = "lane_change"
    LAP = "lap"
    RACE_STOP = "race_stop"
    PIT = "pit"


@dataclass
class RecordedEvent:
    t: float  # seconds since recording start
    address: int
    type: EventType
    value: float = 0.0  # throttle/brake magnitude, lap number, etc.


@dataclass
class Recording:
    name: str
    address: int
    events: list[RecordedEvent] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({
            "name": self.name,
            "address": self.address,
            "events": [asdict(e) for e in self.events],
        }, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Recording":
        data = json.loads(text)
        events = [RecordedEvent(t=e["t"], address=e["address"], type=EventType(e["type"]), value=e.get("value", 0.0))
                  for e in data["events"]]
        return cls(name=data["name"], address=data["address"], events=events)


class InputRecorder:
    def __init__(self, storage_dir: Path | str = "data/recordings"):
        self.storage_dir = Path(storage_dir)
        self._active: dict[int, Recording] = {}
        self._start_time: dict[int, float] = {}

    def start(self, address: int, name: str, now: float) -> None:
        self._active[address] = Recording(name=name, address=address)
        self._start_time[address] = now

    def is_recording(self, address: int) -> bool:
        return address in self._active

    def record(self, address: int, event_type: EventType, value: float, now: float) -> None:
        if address not in self._active:
            return
        t = now - self._start_time[address]
        self._active[address].events.append(RecordedEvent(t=t, address=address, type=event_type, value=value))

    def stop(self, address: int) -> Recording | None:
        recording = self._active.pop(address, None)
        self._start_time.pop(address, None)
        return recording

    def save(self, recording: Recording) -> Path:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        path = self.storage_dir / f"{recording.name}.json"
        path.write_text(recording.to_json())
        return path

    def load(self, name: str) -> Recording:
        path = self.storage_dir / f"{name}.json"
        return Recording.from_json(path.read_text())

    def list_recordings(self) -> list[str]:
        if not self.storage_dir.exists():
            return []
        return sorted(p.stem for p in self.storage_dir.glob("*.json"))
