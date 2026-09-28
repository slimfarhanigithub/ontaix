import { cleanNP, contentWords, domainPrefix, singular, splitList, understand } from './parser';

describe('teach parser', () => {
  it('singular and cleanNP', () => {
    expect(singular('machines')).toBe('machine');
    expect(singular('inspections')).toBe('inspection');
    expect(singular('deliveries')).toBe('delivery');
    expect(singular('batches')).toBe('batch');
    expect(cleanNP('every production line,')).toBe('production line');
    expect(cleanNP('the new sensors')).toBe('sensor');
  });

  it('subject action object with lists and prepositions', () => {
    expect(understand('A line has machines and sensors.')).toEqual([
      { kind: 'rel', subj: 'line', pred: 'has', obj: 'machine' },
      { kind: 'rel', subj: 'line', pred: 'has', obj: 'sensor' },
    ]);
    expect(understand('Materials are bought from suppliers')).toEqual([
      { kind: 'rel', subj: 'material', pred: 'is bought from', obj: 'supplier' },
    ]);
    expect(understand('A plant ships products to customers')).toEqual([
      { kind: 'rel', subj: 'plant', pred: 'ships to', obj: 'customer' },
      { kind: 'rel', subj: 'plant', pred: 'ships', obj: 'product' },
    ]);
  });

  it('specialisations, with and without a rule', () => {
    expect(understand('Operators are employees')).toEqual([{ kind: 'spec', subj: 'operator', obj: 'employee' }]);
    expect(understand('A machine that has run 5,000 hours is a machine due for maintenance')).toEqual([
      { kind: 'spec', subj: 'machine due for maintenance', rule: 'has run 5,000 hours', obj: 'machine' },
    ]);
  });

  it('domain prefix and fallback words', () => {
    expect(domainPrefix('In quality, a defect is raised')).toEqual({ domainKey: 'quality', text: 'a defect is raised' });
    expect(domainPrefix('In HR, people train').domainKey).toBe('people');
    expect(domainPrefix('Plants run lines').domainKey).toBeNull();
    expect(contentWords('The plants have many downtimes!')).toEqual(['plant', 'downtime']);
    expect(splitList('a, b and c')).toEqual(['a', 'b', 'c']);
  });
});
