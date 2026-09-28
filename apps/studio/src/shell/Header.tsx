/**
 * Wordmark, listening status, scene counter, admin button and the "Show changes" button that
 * appears while the panel is hidden. Markup from reference/ontaix-studio-reference.html lines
 * 186-190.
 */
import { SCENES } from '../demo/scenes';
import { refStyle, useStore } from './dom';

export function Header() {
  const st = useStore();
  const { sceneIdx, proposals, listening } = st.ui;
  return (
    <>
      <header>
        <div>
          <div className="wordmark">
            <i></i>Ontaix <small>business as a product</small>
          </div>
          <div className={`status${listening ? ' on' : ''}`} id="status">
            <i></i>
            <span>Listening</span>
          </div>
        </div>
        <div className="scene">
          <span id="sceneNum">{`Scene ${sceneIdx} of ${SCENES.length - 1}`}</span>
          <b id="sceneName">{SCENES[sceneIdx]?.name}</b>
          <div ref={refStyle('margin-top:6px;text-align:right;pointer-events:auto')}>
            <button className="admin-open" id="adminOpen" title="Administration portal (G)" onClick={() => st.openAdmin()}>
              <svg viewBox="0 0 16 16">
                <circle cx="8" cy="8" r="2.2" />
                <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4" />
              </svg>
              Admin portal
            </button>
          </div>
        </div>
      </header>
      <button
        className="legend-toggle"
        id="panelShow"
        ref={refStyle('right:24px;top:calc(18px + env(safe-area-inset-top,0px));bottom:auto;display:none')}
        title="Show the changes panel (P)"
        onClick={() => st.togglePanel()}
      >
        {`Show changes${proposals.length ? ' (' + proposals.length + ')' : ''}`}
      </button>
    </>
  );
}
