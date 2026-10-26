from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Station(Base):
    __tablename__ = 'stations'
    station_id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    direction_label: Mapped[str]
    region: Mapped[str | None]
    coordinates: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Destination(Base):
    __tablename__ = 'destinations'
    destination_id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    category: Mapped[str]
    __table_args__ = (CheckConstraint("category IN ('hospital','market','terminal','station','other')"),)


class DestinationAlias(Base):
    __tablename__ = 'destination_aliases'
    destination_id: Mapped[str] = mapped_column(ForeignKey('destinations.destination_id'), primary_key=True)
    alias: Mapped[str] = mapped_column(primary_key=True)


class Route(Base):
    __tablename__ = 'routes'
    route_id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    direction_label: Mapped[str]


class RouteStop(Base):
    __tablename__ = 'route_stops'
    route_id: Mapped[str] = mapped_column(ForeignKey('routes.route_id'), primary_key=True)
    sequence: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[str] = mapped_column(ForeignKey('stations.station_id'))
    __table_args__ = (CheckConstraint('sequence > 0'),)


class DestinationAccess(Base):
    __tablename__ = 'destination_access'
    destination_id: Mapped[str] = mapped_column(ForeignKey('destinations.destination_id'), primary_key=True)
    station_id: Mapped[str] = mapped_column(ForeignKey('stations.station_id'), primary_key=True)
    distance_meters: Mapped[int | None]
    duration_seconds: Mapped[int | None]
    __table_args__ = (CheckConstraint('distance_meters IS NULL OR distance_meters >= 0'),
                      CheckConstraint('duration_seconds IS NULL OR duration_seconds >= 0'))


class TransferConnection(Base):
    __tablename__ = 'transfer_connections'
    from_route_id: Mapped[str] = mapped_column(primary_key=True)
    from_sequence: Mapped[int] = mapped_column(primary_key=True)
    to_route_id: Mapped[str] = mapped_column(primary_key=True)
    to_sequence: Mapped[int] = mapped_column(primary_key=True)
    evidence: Mapped[str]
    __table_args__ = (
        ForeignKeyConstraint(['from_route_id', 'from_sequence'], ['route_stops.route_id', 'route_stops.sequence']),
        ForeignKeyConstraint(['to_route_id', 'to_sequence'], ['route_stops.route_id', 'route_stops.sequence']),
    )


class RouteSearch(Base):
    __tablename__ = 'route_searches'
    search_id: Mapped[str] = mapped_column(primary_key=True)
    origin_station_id: Mapped[str] = mapped_column(ForeignKey('stations.station_id'))
    destination_id: Mapped[str] = mapped_column(ForeignKey('destinations.destination_id'))
    created_at: Mapped[float]
    expires_at: Mapped[float]
    data_mode: Mapped[str] = mapped_column(String)
    snapshot: Mapped[dict] = mapped_column(JSON)
