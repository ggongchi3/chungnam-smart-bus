import { describe, expect, it } from 'vitest';
import type { RouteOption } from './api/types';
import { boardingWaitSeconds, prototypeEnabled, routeTiming } from './prototypeTiming';
import { prepareDestinations } from './places';

const option: RouteOption = {routeOptionId:'option-1',routeSnapshotVersion:'v1',journeyStatus:'ready',
  routeNames:['20','13'],transferCount:1,totalDurationSeconds:null,walkingDurationSeconds:180,
  estimatedTravelSeconds:900};

describe('시연 시간과 지도 거리 표시', () => {
  it('총시간은 이동시간과 모든 승차 대기의 합이며 같은 경로는 같은 값을 유지한다', () => {
    const timing = routeTiming(option, true);
    expect(timing.waiting).toBe(boardingWaitSeconds('option-1',0) + boardingWaitSeconds('option-1',1));
    expect(timing.total).toBe(900 + timing.waiting!);
    expect(routeTiming({...option}, true)).toEqual(timing);
    expect(timing.waits.every(wait => wait >= 180 && wait <= 420)).toBe(true);
    expect(option.totalDurationSeconds).toBeNull();
  });
  it('실제 live 모드는 미확인 값을 그대로 유지하고 도보에는 버스 대기를 만들지 않는다', () => {
    expect(prototypeEnabled('live')).toBe(false);
    expect(routeTiming(option).total).toBeNull();
    const walk = routeTiming({...option,routeNames:[],transferCount:0},true);
    expect(walk.waiting).toBe(0);
    expect(walk.total).toBe(900);
    expect(walk.waits).toEqual([]);
  });
  it('직선상 가까워도 실제 보행 길이 긴 곳은 뒤로 정렬한다', () => {
    const result = prepareDestinations([
      {destinationId:'a',name:'가병원',category:'hospital',aliases:[],distanceMeters:100,walkingDistanceMeters:600},
      {destinationId:'b',name:'나병원',category:'hospital',aliases:[],distanceMeters:300,walkingDistanceMeters:400},
    ],'walking',true);
    expect(result.map(p => p.destinationId)).toEqual(['b','a']);
    expect(result[0].walkingDistanceBasis).toBe('pedestrian_network');
  });
  it('실제 거리 미확보일 때만 시연 추정값을 사용하고 그 값으로 정렬한다', () => {
    const original = {destinationId:'a',name:'가병원',category:'hospital' as const,aliases:[],distanceMeters:100};
    const estimated = prepareDestinations([original],'walking',true)[0];
    expect(estimated.walkingDistanceMeters).toBe(130);
    expect(estimated.walkingDistanceBasis).toBe('prototype_estimate');
    expect(original).not.toHaveProperty('walkingDistanceMeters');
    expect(prepareDestinations([original],'walking',false)[0].walkingDistanceMeters).toBeUndefined();
  });
});
