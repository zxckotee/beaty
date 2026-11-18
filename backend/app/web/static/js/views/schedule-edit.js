import { h, icon } from '../util.js';
import { mountScheduleEditor } from '../schedule-editor.js';

export async function scheduleEditView(staffId) {
  const root = h('div');
  const body = h('div');
  root.append(
    h(
      'div',
      { class: 'page-head' },
      h('div', null, h('h1', null, 'График мастера'), h('p', { class: 'muted' }, 'Недельное расписание и исключения по датам.')),
      h('button', { class: 'btn sm', type: 'button', onclick: () => { location.hash = '#/team'; } }, icon('chevL'), 'К команде'),
    ),
    body,
  );
  await mountScheduleEditor(body, staffId);
  return root;
}