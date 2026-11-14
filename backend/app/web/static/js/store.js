import { api } from './api.js';

export const store = {
  info: null,
  me: { authenticated: false },
};

export async function loadInfo() {
  store.info = await api.get('/info');
  return store.info;
}

export async function loadMe() {
  store.me = await api.get('/me');
  return store.me;
}

export const isManager = () => store.me.authenticated && store.me.active_role === 'manager';
export const isSpecialist = () => store.me.authenticated && store.me.active_role === 'specialist';
export const isClientRole = () => !store.me.authenticated || store.me.active_role === 'client';
