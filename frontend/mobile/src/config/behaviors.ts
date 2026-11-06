import type { Behavior } from '@/api/types';
import type { IconName } from '@/components/ui';

import { strings } from './strings';

export interface BehaviorMeta {
  key: string;
  label: string;
  icon: IconName;
}

/** The five labels the backend knows (docs/API.md §4), in display order. */
export const BEHAVIORS: BehaviorMeta[] = (
  [
    ['looking_at_phone', 'cellphone-text'],
    ['looking_behind', 'eye-arrow-left-outline'],
    ['turning_around', 'rotate-3d-variant'],
    ['hands_off_wheel', 'steering-off'],
    ['drowsy', 'sleep'],
  ] as const satisfies readonly (readonly [Behavior, IconName])[]
).map(([key, icon]) => ({ key, icon, label: strings.behaviors[key] }));

/** Unknown labels (backend added one) still render, with a generic icon. */
export function behaviorMeta(key: string): BehaviorMeta {
  return (
    BEHAVIORS.find((b) => b.key === key) ?? {
      key,
      icon: 'head-question-outline',
      label: key.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase()),
    }
  );
}
