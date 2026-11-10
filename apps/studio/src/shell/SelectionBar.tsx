/**
 * The selection bar: shown while cells are selected on the canvas with Shift+click or
 * Ctrl+click, an owner addition absent from the reference. It reuses the
 * `.tools` pill row above the tool row and offers one bulk deletion of the selected cells,
 * proposed for approval, and a way to clear the selection. Hidden from the screenshot suite.
 */
import { bulkDeleteSelection } from '../admin/actions';
import { useT } from '../i18n/i18n';
import { BusyButton } from './busy';
import { useStore } from './dom';

export function SelectionBar() {
  const st = useStore();
  const t = useT();
  const n = st.s.selected.size;
  if (!n) return null;
  return (
    <div className="tools sel" id="selBar" data-ox-new="" role="toolbar" aria-label={t('shell.selection.label')}>
      <BusyButton type="button" id="selDelete" title={t('shell.selection.deleteTitle')} onClick={() => bulkDeleteSelection()}>
        {t('shell.selection.deleteSelected', { n })}
      </BusyButton>
      <button type="button" id="selClear" title={t('shell.selection.clearTitle')} onClick={() => st.clearSelection()}>
        {t('shell.selection.clear')}
      </button>
    </div>
  );
}
