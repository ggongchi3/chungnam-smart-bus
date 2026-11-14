import { Fragment, type ReactNode } from 'react';
import type { OptionArrivals, RouteOption, StationRef } from '../../shared/api/types';
import { currentArrival, formatBusLabel, formatDuration } from '../../shared/api/format';
import { routeTiming, simulatedArrivalLabel } from '../../shared/prototypeTiming';
import { displayText } from '../../shared/places';
import s from '../../app/App.module.css';

interface Props {
  options: RouteOption[];
  recommended?: boolean;
  selected: string | null;
  busy: boolean;
  simulate: boolean;
  sortByWait: boolean;
  checkingArrivals: boolean;
  now: number;
  arrivals?: Record<string, OptionArrivals>;
  onChoose: (option: RouteOption) => void;
}

function Icon({file, className = ''}: {file: string; className?: string}) {
  return <span className={`${s.asset} ${s.cardIcon} ${className}`} aria-hidden="true"><img src={`/assets/${file}`} alt="" /></span>;
}

export function RouteCardHeader({names, transferCount, duration, arrival, action}: {
  names: string[]; transferCount: number; duration: number | null; arrival?: string; action: ReactNode;
}) {
  return <span className={s.routeCardHeader}>
    <span className={s.routeCardInfo}>
      <span className={s.routeLine}>
        <span className={s.routeKind}>{names.length ? (transferCount ? `환승 ${transferCount}회` : '직행') : '도보'}</span>
        {names.map((name, index) => <Fragment key={index}>
          {index > 0 && <Icon file="3aff1.svg" className={s.routeBusArrow} />}
          <strong>{formatBusLabel(name).replace(/ 버스$/, '')}</strong>
        </Fragment>)}
      </span>
      <span className={s.routeTimes}>
        <strong aria-label={`예상 이동시간 ${formatDuration(duration)}`}>{duration == null ? '이동시간 확인 불가' : `약 ${formatDuration(duration)}`}</strong>
        {arrival && <span>{arrival}</span>}
      </span>
    </span>
    {action}
  </span>;
}

function stationLabel(station: StationRef) {
  return station.arsId ? `${station.name} ${station.arsId}` : station.name;
}

function visibleRoute(option: RouteOption) {
  if (!option.boardStation || !option.alightStation) return null;
  return JSON.stringify([
    option.routeNames.map(formatBusLabel),
    option.boardStation.stationId,
    (option.transferStations ?? []).map(stop => stop.stationId),
    option.alightStation.stationId,
  ]);
}

export function RouteCards({options, recommended = false, selected, busy, simulate, sortByWait, checkingArrivals, now, arrivals, onChoose}: Props) {
  const cards = options.map(option => {
    const snapshot = arrivals?.[option.routeOptionId];
    const boarding = snapshot?.arrivals[0];
    const firstArrival = snapshot?.routeSnapshotVersion === option.routeSnapshotVersion
      && snapshot.arrivals.length === option.routeNames.length
      && (!option.boardStation || boarding?.boardStationId === option.boardStation.stationId)
      ? currentArrival(boarding, now) : null;
    return {option, firstArrival, wait: firstArrival?.waitSeconds ?? Infinity};
  });
  if (sortByWait) cards.sort((a, b) => a.wait === b.wait ? 0 : a.wait - b.wait);
  const groups = new Map<string, typeof cards>();
  for (const card of cards) {
    const group = card.option.pathGroupId ?? card.option.routeOptionId;
    const variants = groups.get(group);
    if (variants) variants.push(card);
    else groups.set(group, [card]);
  }
  const shownRoutes = new Set<string>();
  const uniqueCards = Array.from(groups.values()).flatMap(variants => {
    const labels = variants.map(({option}) => visibleRoute(option)).filter(label => label !== null);
    if (labels.some(label => shownRoutes.has(label))) return [];
    for (const label of labels) shownRoutes.add(label);
    return [variants[0]];
  });
  const displayedCards = recommended ? uniqueCards.slice(0, 1) : uniqueCards;
  return <div className={s.routeList} role="group" aria-label="이용 가능 경로">{displayedCards.map(({option, firstArrival}) => {
    const timing = routeTiming(option, simulate);
    const stops = option.boardStation && option.alightStation
      ? [option.boardStation, ...(option.transferStations ?? []), option.alightStation] : [];
    const arrival = firstArrival?.label ?? (simulate && arrivals ? simulatedArrivalLabel(option.routeOptionId, 0)
      : checkingArrivals ? '도착 정보 확인 중' : '도착 정보 확인 불가');
    return <button key={option.routeOptionId} className={`${s.comparisonCard} ${recommended ? s.recommendedCard : ''}`} aria-pressed={selected === option.routeOptionId}
      disabled={busy || option.journeyStatus !== 'ready'} onClick={() => onChoose(option)}>
      <RouteCardHeader names={option.routeNames} transferCount={option.transferCount} duration={timing.total ?? timing.movement}
        arrival={option.routeNames.length > 0 ? arrival : undefined}
        action={<span className={s.cardAction}>이 경로 선택하기 <Icon file="d682b.svg" /></span>} />
      {stops.length >= 2 ? <span className={`${s.routeStations} ${stops.length > 2 ? s.routeTransferStations : ''}`}>
        <Icon file={stops.length > 2 ? '51494.svg' : '26246.svg'} className={s.routeStationLine} />
        {stops.map((stop, index) => {
          const last = index === stops.length - 1;
          const direction = last ? null : option.directionLabels?.[index];
          return <span className={s.routeStation} key={`${stop.stationId}-${index}`}>
            <Icon file={index === 0 ? '92c82.svg' : 'a8aeb.svg'} />
            <span className={s.routeStationDetails}>
              <span>{stationLabel(stop)}</span>
              {direction && <small>{index > 0 ? '환승 · ' : ''}{direction}</small>}
            </span>
          </span>;
        })}
      </span> : <span className={s.routeStationText}>{option.routeNames.length
        ? '정류장은 상세 안내에서 확인해 주세요.' : '현재 정류장에서 목적지까지 도보 이동'}</span>}
      {option.reasonText && <span className={s.routeReason}>{displayText(option.reasonText)}</span>}
    </button>;
  })}</div>;
}
