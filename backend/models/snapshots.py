"""Internal persisted search schema; the existing JSON layout stays compatible."""
from typing import Annotated

from pydantic import Field, model_validator

from backend.models import schemas as s

Sequence = Annotated[int, Field(strict=True, ge=1)]


class SavedRouteOption(s.Model):
    detail: s.RouteDetail
    legs: list[tuple[s.Identifier, Sequence, Sequence]] = Field(min_length=1, max_length=2)
    accessStationId: s.Identifier

    @model_validator(mode='after')
    def consistent_path(self):
        segments = self.detail.segments
        expected_types = ['bus', 'walk'] if len(self.legs) == 1 else ['bus', 'transfer', 'bus', 'walk']
        if [p.type for p in segments] != expected_types:
            raise ValueError('Stored segment order does not match bus legs')
        if len({p.segmentId for p in segments}) != len(segments):
            raise ValueError('Stored segment IDs are not unique')
        buses = [p for p in segments if p.type == 'bus']
        for bus, (route_id, board, alight) in zip(buses, self.legs):
            if board >= alight or (bus.routeId, bus.boardSequence, bus.alightSequence) != (route_id, board, alight):
                raise ValueError('Stored bus leg references disagree')
        if (buses[0].boardStation.stationId != self.detail.originStationId or
                buses[-1].alightStation.stationId != self.accessStationId):
            raise ValueError('Stored origin or destination access disagrees')
        if len(buses) == 2:
            transfer = segments[1]
            if (transfer.fromSegmentId != buses[0].segmentId or transfer.toSegmentId != buses[1].segmentId or
                    transfer.atStation != buses[0].alightStation or transfer.atStation != buses[1].boardStation):
                raise ValueError('Stored transfer references disagree')
        if segments[-1].fromLabel != buses[-1].alightStation.name:
            raise ValueError('Stored destination walking link disagrees')
        if self.detail.journeyStatus != 'ready':
            raise ValueError('Stored path was not ready at search time')
        return self
