/**
 * The fixed-width Enable/Disable toggle (`tgBtn`) and the setting row (`setRow`) of
 * reference/ontaix-studio-reference.html lines 954-956.
 */
import type { ButtonHTMLAttributes } from 'react';

import type { Settings } from '../api/types';
import { useStore } from '../shell/dom';
import { changeSetting } from './actions';

type TgProps = { on: boolean; locked?: boolean } & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'className' | 'disabled' | 'title'>;

/** Shows `Disable` with a green dot when on, `Enable` when off; a locked toggle is disabled and reads `Always on`. */
export function Tg({ on, locked, ...rest }: TgProps) {
  return (
    <button
      className={`tg${on ? '' : ' off'}`}
      {...rest}
      disabled={locked || undefined}
      title={locked ? 'Always on' : undefined}
      aria-pressed={on ? 'true' : 'false'}
    >
      <i></i>
      {on ? 'Disable' : 'Enable'}
    </button>
  );
}

export type SettingKey = keyof Omit<Settings, 'refresh'>;

/** A tenant setting with its toggle; locked settings are always on. */
export function SetRow({ k, title, desc, locked }: { k: SettingKey; title: string; desc: string; locked?: boolean }) {
  const st = useStore();
  const on = locked ? true : !!st.ui.settings?.[k];
  return (
    <div className="set">
      <b>{title}</b>
      <Tg on={on} locked={locked} data-set={k} onClick={() => changeSetting(k)} />
      <p>{desc}</p>
    </div>
  );
}
