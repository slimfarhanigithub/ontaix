/**
 * The new-concept box (click a cell, grow a concept from it) and the relationship dialog
 * (drop one cell on another). Markup from reference/ontaix-studio-reference.html lines
 * 215-221; behaviour from `openNewBox` / `submitNew` (lines 689-700) and `openLinkBox` /
 * `submitLink` / `deleteLink` (lines 705-730).
 */
import { useEffect, useRef, useState } from 'react';

import type { DomainKey } from '../api/types';
import { domainOf, find } from '../canvas/state';
import { suggestAction } from '../nl/suggest';
import { refStyle, titleCase, useStore } from './dom';

const SUGGEST_ICON = (
  <svg viewBox="0 0 16 16">
    <path d="M8 2l1.2 3.3L12.5 6.5 9.2 7.7 8 11 6.8 7.7 3.5 6.5l3.3-1.2zM13 10l.6 1.4 1.4.6-1.4.6L13 14l-.6-1.4-1.4-.6 1.4-.6zM3 11l.5 1 1 .5-1 .5-.5 1-.5-1-1-.5 1-.5z" />
  </svg>
);

export function NewBox() {
  const st = useStore();
  const s = st.s;
  const box = st.ui.newBox;
  const host = box?.host ?? null;
  const [name, setName] = useState('');
  const [action, setAction] = useState('');
  const [domain, setDomain] = useState('');
  const nameRef = useRef<HTMLInputElement>(null);
  const actionRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!box) return;
    setName('');
    setAction('');
    const list = host?.company ? host.company.domains : s.DOMAINS;
    setDomain(host?.domain ? host.domain.key : list[0]?.key ?? '');
    const t = setTimeout(() => nameRef.current?.focus(), 30);
    return () => clearTimeout(t);
    // Reopening for another host resets the fields.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [box]);

  const submit = (spec: boolean) => {
    if (!host || !host.sid || !host.company?.sid) return;
    const nm = titleCase(name.trim());
    if (!nm) {
      nameRef.current?.focus();
      return;
    }
    const act = action.trim().toLowerCase();
    const dom = domain;
    st.closeNewBox();
    if (find(s, nm, host.company)) {
      st.caption('Already there', `${nm} is already in the model. Drop ${host.label} onto it to relate them instead.`);
      return;
    }
    const domName = domainOf(s, dom, host.company)?.name ?? dom;
    if (spec) {
      void st.propose({
        type: 'spec',
        companyId: host.company.sid,
        parentId: host.sid,
        label: nm,
        rule: act || '',
        domainKey: dom as DomainKey,
        caption: `${host.label} divides: ${nm} inherits everything ${host.label} is.`,
      });
      st.caption('One proposal', `${nm}, a specialisation of ${host.label}, is waiting for your approval.`);
    } else {
      void st.propose({
        type: 'concept',
        companyId: host.company.sid,
        parentId: host.sid,
        label: nm,
        domainKey: dom as DomainKey,
        action: act || 'relates to',
        caption: `${nm} is kept in ${domName}.`,
      });
      st.caption('One proposal', `${host.label} ${act || 'relates to'} ${nm}, in ${domName}, is waiting for your approval.`);
    }
  };

  const onKey = (field: 'name' | 'action') => (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (field === 'name' && !action) actionRef.current?.focus();
      else submit(false);
    }
    if (e.key === 'Escape') st.closeNewBox();
  };

  const domains = host?.company ? host.company.domains : s.DOMAINS;
  return (
    <div
      className={`linkbox${box ? ' on' : ''}`}
      id="newbox"
      style={box ? { left: `${box.left}px`, top: `${box.top}px` } : undefined}
    >
      <button className="x" id="nbCancel" aria-label="Close" onClick={() => st.closeNewBox()}>
        ×
      </button>
      <div className="pair">
        <b id="nbFrom">{host?.label ?? ''}</b>
        <i>divides into</i>
        <b id="nbPreview">{name.trim() || '…'}</b>
      </div>
      <div className="row">
        <input
          id="nbName"
          placeholder="new concept, e.g. Batch"
          ref={nameRef}
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={onKey('name')}
        />
      </div>
      <div className="row" ref={refStyle('margin-top:6px')}>
        <input
          id="nbAction"
          placeholder="action from the parent, e.g. produced in"
          ref={actionRef}
          value={action}
          onChange={(e) => setAction(e.target.value)}
          onKeyDown={onKey('action')}
        />
        <button
          type="button"
          className="ico"
          id="nbSuggest"
          title="Suggest an action (you can still edit it)"
          onClick={() => {
            if (!host) return;
            const nm = name.trim();
            if (!nm) {
              st.toast2('<b>Name first</b> the suggestion depends on the new concept’s name');
              nameRef.current?.focus();
              return;
            }
            setAction(suggestAction(s, host.label, nm, host, find(s, nm, host.company)));
            setTimeout(() => {
              actionRef.current?.focus();
              actionRef.current?.select();
            }, 0);
          }}
        >
          {SUGGEST_ICON}
        </button>
        <select id="nbDomain" aria-label="Domain product" value={domain} onChange={(e) => setDomain(e.target.value)}>
          {domains.map((d) => (
            <option key={d.key} value={d.key}>
              {d.name}
            </option>
          ))}
        </select>
      </div>
      <div className="row" ref={refStyle('margin-top:6px')}>
        <button id="nbGo" onClick={() => submit(false)}>
          Propose
        </button>
        <button className="cancel" id="nbSpec" title="The new cell inherits everything the parent is" onClick={() => submit(true)}>
          Specialisation
        </button>
      </div>
    </div>
  );
}

export function LinkBox() {
  const st = useStore();
  const s = st.s;
  const box = st.ui.linkBox;
  const [action, setAction] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const link = box?.link ?? null;
  const structural = !!link && (link.kind === 'isa' || link.kind === 'same');

  useEffect(() => {
    if (!box) return;
    setAction(box.link ? box.link.label : '');
    if (!structural) {
      const t = setTimeout(() => input.current?.focus(), 30);
      return () => clearTimeout(t);
    }
    // Reopening for another pair resets the field.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [box?.a, box?.b, box?.link]);

  const submitLink = (reverseNow?: boolean) => {
    if (!box) return;
    const reverse = reverseNow ?? box.reverse;
    const v = action.trim().toLowerCase() || (link ? link.label : '');
    if (!v) return;
    const { a, b } = box;
    st.closeLinkBox();
    if (!link && a.company !== b.company && st.ui.settings && !st.ui.settings.crossCompany) {
      st.toast2('<b>Not allowed</b> companies may not interact · enable it in the admin portal');
      return;
    }
    if (link) {
      if (v === link.label && !reverse) return;
      const from = reverse ? b : a,
        to = reverse ? a : b;
      if (link.sid)
        void st.propose({
          type: 'change',
          changeKind: 'edit_relation',
          payload: { relationId: link.sid, action: v, reverse },
          caption: `The relation now reads ${from.label} ${v} ${to.label}.`,
        });
      st.caption('One proposal', `Changing “${link.label}” to “${v}”${reverse ? ' and reversing the direction' : ''} is waiting for your approval.`);
      return;
    }
    if (s.links.some((l) => l.a === a && l.b === b && l.label === v)) {
      st.caption('Already there', `${a.label} ${v} ${b.label} is already in the model.`);
      return;
    }
    const from = reverse ? b : a,
      to = reverse ? a : b;
    if (from.sid && to.sid)
      void st.propose({
        type: 'relation',
        aId: from.sid,
        bId: to.sid,
        aLabel: from.label,
        bLabel: to.label,
        action: v,
        caption:
          from.company !== to.company
            ? `${from.label} (${from.company?.name}) ${v} ${to.label} (${to.company?.name}): a relation across two companies.`
            : `${from.label} ${v} ${to.label}${from.domain !== to.domain ? ': a relation across two domain products' : ''}.`,
      });
    st.caption('One proposal', `${from.label} ${v} ${to.label} is waiting for your approval.`);
  };

  const deleteLink = () => {
    if (!box || !link) return;
    const { a, b } = box;
    st.closeLinkBox();
    if (link.sid) void st.propose({ type: 'change', changeKind: 'remove_relation', payload: { relationId: link.sid } });
    st.caption('One proposal', `Removing “${a.label} ${link.label} ${b.label}” is waiting for your approval.`);
  };

  const from = box ? (box.reverse ? box.b : box.a) : null,
    to = box ? (box.reverse ? box.a : box.b) : null;
  return (
    <div
      className={`linkbox${box ? ' on' : ''}`}
      id="linkbox"
      style={box ? { left: `${box.left}px`, top: `${box.top}px` } : undefined}
    >
      <button className="x" id="lbCancel" aria-label="Close" onClick={() => st.closeLinkBox()}>
        ×
      </button>
      <div className="pair">
        <b id="lbA">{from?.label ?? ''}</b>
        <button
          type="button"
          className={`ico${box?.reverse ? ' on' : ''}`}
          id="lbReverse"
          title={link && link.kind === 'isa' ? 'Reverse: make the other one the parent' : 'Reverse direction'}
          style={{ display: link && link.kind === 'same' ? 'none' : undefined }}
          onClick={() => {
            st.reverseLinkBox();
            if (structural) submitLink(!box?.reverse);
          }}
        >
          <svg viewBox="0 0 16 16">
            <path d="M2 5.5h9l-3-3M14 10.5H5l3 3" />
          </svg>
        </button>
        <b id="lbB">{to?.label ?? ''}</b>
      </div>
      <div className="row">
        <input
          id="lbAction"
          placeholder="action, e.g. uses, produces, belongs to"
          ref={input}
          value={action}
          readOnly={structural}
          style={{ opacity: structural ? 0.5 : 1 }}
          onChange={(e) => setAction(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              submitLink();
            }
            if (e.key === 'Escape') st.closeLinkBox();
          }}
        />
        <button
          type="button"
          className="ico"
          id="lbSuggest"
          title="Suggest an action (you can still edit it)"
          style={{ display: structural ? 'none' : undefined }}
          onClick={() => {
            if (!from || !to) return;
            setAction(suggestAction(s, from.label, to.label, from, to));
            setTimeout(() => {
              input.current?.focus();
              input.current?.select();
            }, 0);
          }}
        >
          {SUGGEST_ICON}
        </button>
        <button
          type="button"
          className="ico go"
          id="lbGo"
          title={link ? 'Propose change' : 'Propose'}
          style={{ display: structural ? 'none' : undefined }}
          onClick={() => submitLink()}
        >
          <svg viewBox="0 0 16 16">
            <path d="M2.5 8.5l3.5 3.5 7.5-8" />
          </svg>
        </button>
      </div>
      <div className="row" id="lbDanger" style={{ marginTop: 8, display: link ? 'flex' : 'none' }}>
        <button type="button" className="cancel" id="lbDelete" style={{ color: 'var(--conflict)' }} onClick={deleteLink}>
          Delete this relation
        </button>
      </div>
    </div>
  );
}
