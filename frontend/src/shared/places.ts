import catalog from '../../../shared/data/cheonan-places.json';
import type { Destination, RouteDetail, GuidanceData } from './api/types';

export type PlaceCategory = 'hospital' | 'office' | 'terminal' | 'market' | 'station' | 'education' | 'culture' | 'shopping';
export const SERVICE_REGION = catalog.region;
export const CATEGORY_LABELS: Record<PlaceCategory, string> = { hospital:'병원', office:'관공서', terminal:'터미널', market:'시장·쇼핑', station:'역', education:'대학·교육', culture:'관광·문화', shopping:'쇼핑' };
export const places = catalog.places;
export const placeById = new Map(places.map(place => [place.destinationId, place]));

/** Presentation only. API payloads, saved snapshots and their IDs stay intact. */
export function displayText(text: string): string {
  return text.replace(/시연 데이터\s*·\s*실제 운행 정보 아님[.。\s]*/g, '')
    .replace(/(?:시연|테스트용|가상 시설|더미 데이터)\s*/g, '').trim();
}
export function withPlaceDetails(destination: Destination): Destination {
  const place = placeById.get(destination.destinationId);
  return { ...destination, name: displayText(destination.name),
    ...(place ? { address:place.address, placeKind:place.kind as PlaceCategory, locationNote:place.locationNote,
      sourceUrl:place.sourceUrl, sourceName:place.sourceName } : {}) };
}
export function displayDetail(detail: RouteDetail): RouteDetail {
  return { ...detail, segments: detail.segments.map(segment => segment.type === 'bus'
    ? { ...segment, routeName:displayText(segment.routeName), boardStation:{...segment.boardStation,name:displayText(segment.boardStation.name)}, alightStation:{...segment.alightStation,name:displayText(segment.alightStation.name)} }
    : segment.type === 'transfer' ? { ...segment, atStation:{...segment.atStation,name:displayText(segment.atStation.name)} }
    : { ...segment, fromLabel:displayText(segment.fromLabel), toLabel:displayText(segment.toLabel) }) };
}
export function displayGuidance(guidance: GuidanceData): GuidanceData {
  return { ...guidance, steps:guidance.steps.map(step => ({ ...step, text:displayText(step.text) })) };
}
