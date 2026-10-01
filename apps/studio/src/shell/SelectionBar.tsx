/**
 * The selection bar: shown while cells are selected on the canvas with Shift+click or
 * Ctrl+click, an owner addition absent from the reference. It reuses the
 * `.tools` pill row above the tool row and offers one bulk deletion of the selected cells,
 * proposed for approval, and a way to clear the selection. Hidden from the screenshot suite.
 */
import { bulkDeleteSelection } from '../admin/actions';
import { BusyButton } from './busy';
import { useStore } from './dom';

export function SelectionBar() {
  const st = useStore();
  const n = st.s.selected.size;
  if (!n) return null;
  return (
    <div className="tools sel" id="selBar" data-ox-new="" role="toolbar" aria-label="Selected cells">
      <BusyButton type="button" id="selDelete" title="Propose deleting the selected cells" onClick={() => bulkDeleteSelection()}>
        {`Delete selected (${n})`}
      </BusyButton>
      <button type="button" id="selClear" title="Clear the selection (Escape)" onClick={() => st.clearSelection()}>
        Clear selection
      </button>
    </div>
  );
}
