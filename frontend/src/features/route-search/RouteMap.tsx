import type { Coordinates, RouteDetail } from '../../shared/api/types';
import { formatBusLabel, formatStation } from '../../shared/api/format';
import styles from './RouteMap.module.css';

type Point = [number, number];
const width = 600, height = 296, padding = 28;

function projector(coordinates: Coordinates[]) {
  const origin = coordinates[0];
  const longitudeScale = Math.cos(origin.latitude * Math.PI / 180);
  const relative = ({ latitude, longitude }: Coordinates): Point => [
    (longitude - origin.longitude) * longitudeScale, origin.latitude - latitude,
  ];
  const points = coordinates.map(relative);
  const xs = points.map(point => point[0]), ys = points.map(point => point[1]);
  const left = Math.min(...xs), top = Math.min(...ys);
  const spanX = Math.max(...xs) - left, spanY = Math.max(...ys) - top;
  const scale = Math.min((width - padding * 2) / (spanX || 1e-8), (height - padding * 2) / (spanY || 1e-8));
  return (position: Coordinates): Point => {
    const [x, y] = relative(position);
    return [(width - spanX * scale) / 2 + (x - left) * scale, (height - spanY * scale) / 2 + (y - top) * scale];
  };
}

function arrow(points: Point[]) {
  const lengths = points.slice(1).map(([x, y], i) => Math.hypot(x - points[i][0], y - points[i][1]));
  let remaining = lengths.reduce((sum, length) => sum + length, 0) / 2;
  for (const [i, length] of lengths.entries()) {
    if (length > 0 && remaining <= length) {
      const [x, y] = points[i], [nextX, nextY] = points[i + 1];
      const angle = Math.atan2(nextY - y, nextX - x) * 180 / Math.PI;
      return `translate(${x + (nextX - x) * remaining / length} ${y + (nextY - y) * remaining / length}) rotate(${angle})`;
    }
    remaining -= length;
  }
  return undefined;
}

export function RouteMap({ detail }: { detail: RouteDetail }) {
  const buses = detail.segments.filter(segment => segment.type === 'bus');
  if (detail.dataSource !== 'cheonan-bis-static' || !buses.length) return null;
  const coordinates = buses.flatMap(bus => [...(bus.path ?? []), ...(bus.stops ?? []).map(stop => stop.coordinates)]);
  const project = coordinates.length ? projector(coordinates) : null;
  const hasPath = buses.some(bus => (bus.path?.length ?? 0) >= 2);
  return <section className={styles.map} aria-label="버스 운행 경로">
    <h2>버스 운행 경로</h2>
    {project && hasPath && <svg className={styles.diagram} viewBox={`0 0 ${width} ${height}`} role="img"
      aria-label="선택한 버스 경로 지도. 점은 정류장, 화살표는 진행 방향을 나타냅니다.">
      <text x={width - 23} y="22" textAnchor="middle" fill="currentColor" fontSize="16">↑</text>
      <text x={width - 23} y="42" textAnchor="middle" fill="currentColor" fontSize="13">북</text>
      {buses.map((bus, index) => {
        const points = (bus.path ?? []).map(project);
        return points.length < 2 ? null : <polyline key={bus.segmentId} className={index ? styles.transfer : styles.first}
          points={points.map(point => point.join(',')).join(' ')} fill="none" stroke="currentColor" strokeWidth="6"
          strokeLinejoin="round" strokeLinecap="round" />;
      })}
      {buses.map((bus, index) => {
        const points = (bus.path ?? []).map(project);
        const transform = arrow(points);
        return <g key={bus.segmentId} className={index ? styles.transfer : styles.first}>
          {bus.stops?.map((stop, i, stops) => {
            const [x, y] = project(stop.coordinates);
            const end = i === 0 || i === stops.length - 1;
            return <circle key={stop.sequence} cx={x} cy={y} r={end ? 7 : 3.5} className={styles.station}
              stroke="currentColor" strokeWidth={end ? 3.5 : 2}><title>{formatStation(stop)}</title></circle>;
          })}
          {transform && <path transform={transform} d="M -7 -8 L 3 0 L -7 8" fill="none"
            stroke="currentColor" className={styles.arrow} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />}
        </g>;
      })}
    </svg>}
    {hasPath && <ol className={styles.legend}>
      {buses.map((bus, index) => <li key={bus.segmentId}>
        <span className={index ? styles.transfer : styles.first} aria-hidden="true">●</span>
        <strong>{formatBusLabel(bus.routeName)}</strong> {formatStation(bus.boardStation)} → {formatStation(bus.alightStation)}
      </li>)}
    </ol>}
    <p>{hasPath ? '천안시 노선 자료 · 화살표는 버스 진행 방향이에요.' : '공개 자료에서 이 구간의 지도 경로를 확인할 수 없어요.'}</p>
    {hasPath && buses.some(bus => (bus.path?.length ?? 0) < 2) && <p>지도 자료가 없는 구간은 위 정차 순서에서 확인해 주세요.</p>}
  </section>;
}
