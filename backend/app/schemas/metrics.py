# backend/app/schemas/metrics.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CurrentMetricsResponse(BaseModel):
    cpu: Optional[float] = None
    memory: Optional[float] = None
    request_count: Optional[float] = None
    collected_at: datetime
