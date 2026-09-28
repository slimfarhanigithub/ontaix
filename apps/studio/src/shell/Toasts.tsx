/**
 * Transient confirmations at the bottom of the screen. Markup from
 * reference/ontaix-studio-reference.html line 191; behaviour from `toast2` (line 915).
 */
import { useStore } from './dom';

export function Toasts() {
  const st = useStore();
  return (
    <div className="toasts2" id="toasts2">
      {st.ui.toasts.map((t) => (
        <div key={t.id} className="toast2" dangerouslySetInnerHTML={{ __html: t.html }} />
      ))}
    </div>
  );
}
