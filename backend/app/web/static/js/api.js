const tenant = location.pathname.split('/')[2] || '';
export const tenantId = tenant;
const base = `/api/t/${encodeURIComponent(tenant)}`;

export class ApiError extends Error {
  constructor(status, detail, code) {
    super(detail);
    this.status = status;
    this.code = code;
  }
}

const MESSAGES = {
  CellOverlapError: 'У этого специалиста уже есть ячейка в это время.',
  CellInUseError: 'В ячейке есть записи: сначала отмените их.',
  SlotTakenError: 'Это время только что заняли. Выберите другое окно.',
  DoesNotFitError: 'Выбранные услуги уже не помещаются в это окно.',
  NotFoundError: 'Не найдено. Обновите страницу.',
  ValidationError: 'Проверьте введённые данные.',
  ForbiddenError: 'Действие недоступно.',
  ConflictError: 'Такая запись уже существует.',
};

const DETAIL_MESSAGES = {
  'cancel deadline passed': 'Отменить запись уже нельзя: слишком близко к началу визита.',
  'cell is in the past': 'Нельзя создать ячейку в прошлом.',
  'phone is required': 'Укажите номер телефона.',
  'subscription inactive; renew to change data': 'Подписка неактивна: изменения временно недоступны.',
  'cell must still cover existing bookings': 'Ячейка должна по-прежнему покрывать существующие записи.',
  'cannot change specialist: cell has bookings': 'Нельзя сменить специалиста: в ячейке есть записи.',
  'too many requests': 'Слишком много попыток. Подождите минуту.',
};

export function friendly(err) {
  if (err instanceof ApiError) return DETAIL_MESSAGES[err.message] || MESSAGES[err.code] || err.message || 'Ошибка запроса';
  return 'Нет связи с сервером';
}

async function request(method, path, body, isForm = false) {
  const opts = { method, credentials: 'same-origin', headers: {} };
  if (body !== undefined) {
    if (isForm) opts.body = body;
    else {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
  }
  const res = await fetch(`${base}${path}`, opts);
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = data && typeof data.detail === 'string' ? data.detail : res.statusText;
    throw new ApiError(res.status, detail, data && data.code);
  }
  return data;
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body ?? {}),
  patch: (path, body) => request('PATCH', path, body),
  put: (path, body) => request('PUT', path, body),
  del: (path) => request('DELETE', path),
  upload: (path, file) => {
    const form = new FormData();
    form.append('file', file);
    return request('POST', path, form, true);
  },
};
