from __future__ import annotations

import json
from pathlib import Path

from app.models import Lead, MessageRecord, StoreData


class JsonStorage:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save(StoreData())

    def load(self) -> StoreData:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return StoreData.model_validate(raw)
        except (json.JSONDecodeError, FileNotFoundError):
            data = StoreData()
            self.save(data)
            return data

    def save(self, data: StoreData) -> None:
        self.path.write_text(
            json.dumps(data.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )

    def list_leads(self) -> list[Lead]:
        return self.load().leads

    def get_lead(self, lead_id: str) -> Lead | None:
        data = self.load()
        return next((lead for lead in data.leads if lead.id == lead_id), None)

    def create_lead(self, lead: Lead) -> Lead:
        data = self.load()
        data.leads.append(lead)
        self.save(data)
        return lead

    def update_lead(self, updated_lead: Lead) -> Lead:
        data = self.load()
        data.leads = [
            updated_lead if lead.id == updated_lead.id else lead
            for lead in data.leads
        ]
        self.save(data)
        return updated_lead

    def list_messages_for_lead(self, lead_id: str) -> list[MessageRecord]:
        data = self.load()
        return [message for message in data.messages if message.lead_id == lead_id]

    def add_message(self, message: MessageRecord) -> MessageRecord:
        data = self.load()
        data.messages.append(message)
        self.save(data)
        return message