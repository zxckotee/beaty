import { h, icon } from '../util.js';
import { navigate, navigateDashboardSection } from '../main.js';
import { mountScheduleEditor } from '../schedule-editor.js';

export async function scheduleEditView(staffId) {
  const root = h('div');
  const body = h('div');
  root.append(
    h(
      'div',
      { class: 'page-head' },
      h('div', null,
        h('h1', null, 'График мастера'),
        h('p', { class: 'muted' }, 'Назначьте правила по дням недели. Исключения по датам — ниже.'),
      ),
      h('div', { class: 'row wrap', style: { gap: '8px' } },
        h('button', { class: 'btn sm soft', type: 'button', onclick: () => navigate('dashboard/rules') }, 'Шаблоны смен'),
        h('button', { class: 'btn sm', type: 'button', onclick: () => navigateDashboardSection('dash-team') }, icon('chevL'), 'К специалистам'),
      ),
    ),
    body,
  );
  await mountScheduleEditor(body, staffId);
  return root;
}