/**
 * The fixed-width Enable/Disable toggle (`tgBtn`) and the setting row (`setRow`) of
 * reference/ontaix-studio-reference.html lines 954-956.
 */
import type { ButtonHTMLAttributes } from 'react';

import type { Settings } from '../api/types';
import { useBusyAction } from '../shell/busy';
import { useStore } from '../shell/dom';
import { changeSetting } from './actions';

type TgProps = { on: boolean; locked?: boolean; onClick?: () => unknown } & Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  'className' | 'disabled' | 'title' | 'onClick'
>;

/**
 * Shows `Disable` with a green dot when on, `Enable` when off; a locked toggle is disabled and
 * reads `Always on`. While an awaited click is pending past the busy delay, the spinner stands
 * in the dot's place so the label keeps the toggle's fixed width.
 */
export function Tg({ on, locked, onClick, ...rest }: TgProps) {
  const { shown, run } = useBusyAction();
  return (
    <button
      className={`tg${on ? '' : ' off'}`}
      {...rest}
      disabled={locked || shown || undefined}
      aria-busy={shown ? 'true' : undefined}
      title={locked ? 'Always on' : undefined}
      aria-pressed={on ? 'true' : 'false'}
      onClick={onClick ? () => run(onClick) : undefined}
    >
      {shown ? <span className="spin"></span> : <i></i>}
      {on ? 'Disable' : 'Enable'}
    </button>
  );
}

export type SettingKey = keyof Omit<Settings, 'refresh'>;

/** A tenant setting with its toggle; locked settings are always on. A row marked `ox` is an owner addition hidden from the screenshot suite. */
export function SetRow({ k, title, desc, locked, ox }: { k: SettingKey; title: string; desc: string; locked?: boolean; ox?: boolean }) {
  const st = useStore();
  const on = locked ? true : !!st.ui.settings?.[k];
  return (
    <div className="set" data-ox-new={ox ? '' : undefined}>
      <b>{title}</b>
      <Tg on={on} locked={locked} data-set={k} onClick={() => changeSetting(k)} />
      <p>{desc}</p>
    </div>
  );
}
