const $ = (id) => document.getElementById(id);
const tr = caixaUI.t;
const money = (value) => Number(value).toLocaleString(caixaUI.formatLocale, {style: 'currency', currency: 'BRL'});
const quantity = (value) => Number(value).toLocaleString(caixaUI.formatLocale, {maximumFractionDigits: 3});
function quantityWithUnit(value, unit = 'unidade') {
  const units = caixaUI.locale === 'en' ? {
    unidade: ['unit', 'units'], un: ['unit', 'units'], kg: ['kilogram', 'kilograms'],
    g: ['gram', 'grams'], l: ['liter', 'liters'], ml: ['milliliter', 'milliliters'],
    pacote: ['package', 'packages'], caixa: ['box', 'boxes'], dz: ['dozen', 'dozens'],
  } : {
    unidade: ['unidade', 'unidades'], un: ['unidade', 'unidades'],
    kg: ['quilograma', 'quilogramas'], g: ['grama', 'gramas'],
    l: ['litro', 'litros'], ml: ['mililitro', 'mililitros'],
    pacote: ['pacote', 'pacotes'], caixa: ['caixa', 'caixas'], dz: ['dúzia', 'dúzias'],
  };
  const label = units[unit.trim().toLowerCase()];
  return `${quantity(value)} ${label ? label[Number(value) === 1 ? 0 : 1] : unit}`;
}
function isCountUnit(unit = 'unidade') {return ['unidade', 'un', 'pacote', 'caixa', 'dz'].includes(unit.trim().toLowerCase());}
function validHistoryQuantity() {
  const value = $('history-quantity').value;
  const n = Number(value);
  return !value && !$('history-quantity').validity?.badInput || !!value && Number.isFinite(n) && n > 0 && Math.abs(n * 1000 - Math.round(n * 1000)) < 0.000001;
}
let pendingSale = null;
let currentUserId = '';
function savePending(value) {
  pendingSale = value;
  if (value) sessionStorage.setItem('caixa-pending-sale', JSON.stringify(value));
  else sessionStorage.removeItem('caixa-pending-sale');
}
let lastMessage = null;
let lastHistory = null;
let lastHistoryKey = '';
let lastSale = null;
let historyErrorKey = '';
let token = sessionStorage.getItem('caixa-token') || '';
let products = [];
let cart = new Map();
let busy = false;
let loading = false;
let syncing = false;
let historySnapshot = '';
let historyPage = 1;
let historyTotal = 0;
let historyMarket = '';
let historyLoading = false;
let historyRequest = 0;
let historySearchTimer;
const HISTORY_PAGE_SIZE = 7;
let saleToastTimer;
let syncPending = false;
let eventController;
let reconnectTimer;

function stopEvents() {
  clearTimeout(reconnectTimer);
  eventController?.abort();
  eventController = undefined;
}
async function startEvents() {
  if (!token || eventController) return;
  const session = token;
  const controller = new AbortController();
  eventController = controller;
  try {
    const response = await fetch('/api/events', {
      headers: {Authorization: 'Bearer ' + session}, signal: controller.signal,
    });
    if (response.status === 401) {
      if (token === session) {logout(); message('Sua sessão expirou. Entre novamente.', true);}
      return;
    }
    if (!response.ok || !response.body) throw new Error('Conexão de eventos indisponível');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    try {
      while (token === session && !controller.signal.aborted) {
        const {value, done} = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, {stream: true});
        let end;
        while ((end = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, end);
          buffer = buffer.slice(end + 2);
          if (/^event: (ready|change)$/m.test(frame)) requestSync();
        }
      }
    } finally {await reader.cancel().catch(() => {}); reader.releaseLock();}
  } catch {
    // Reconecta apenas se a conexão cair; não consulta vendas periodicamente.
  } finally {
    if (eventController === controller) {
      eventController = undefined;
      if (token === session && !controller.signal.aborted) reconnectTimer = setTimeout(startEvents, 3000);
    }
  }
}
function requestSync() {
  syncPending = true;
  void syncData();
}
function flushSync() {
  if (syncPending && !syncing && canSync()) void syncData();
}

function hideSaleToast() {
  clearTimeout(saleToastTimer);
  $('sale-toast').hidden = true;
}
function showSaleToast() {
  hideSaleToast();
  $('sale-toast').hidden = false;
  saleToastTimer = setTimeout(hideSaleToast, 3000);
}

function updateMarkets(markets) {
  const previous = $('market').value;
  const next = markets.some(m => m.id === previous) ? previous : (markets[0]?.id || '');
  const entries = markets.length ? markets : [{id: '', name: tr('Nenhum mercado cadastrado')}];
  const options = [...$('market').options];
  if (options.length !== entries.length || entries.some((m, i) => options[i]?.value !== m.id || options[i]?.textContent !== m.name)) {
    $('market').replaceChildren(...entries.map(m => {
      const option = el('option', m.name); option.value = m.id; return option;
    }));
  }
  $('market').value = next;
  $('market').disabled = busy || loading || !!pendingSale || !next;
  $('empty-markets').hidden = markets.length > 0;
  if (previous !== next) {
    cart.clear();
    $('receipt').hidden = true;
  }
  return previous !== next;
}
function reconcileCart() {
  if (pendingSale) return;
  let removed = false;
  for (const [id, qty] of cart) {
    const p = products.find(p => p.id === id);
    if (!p || Number(p.stock) < qty) {cart.delete(id); removed = true;}
  }
  if (removed) message('Alguns itens foram removidos do carrinho porque o produto ou o estoque disponível mudou.', true);
}

function message(key, error = false, values = {}) {
  lastMessage = {key, error, values};
  const text = tr(key, {...values, ...(values.error ? {error: tr(values.error)} : {})});
  $('message').textContent = text;
  $('message').className = error ? 'error' : '';
  $('message').hidden = !text;
}
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
async function api(path, body, idempotencyKey) {
  const response = await fetch('/api' + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {'Content-Type': 'application/json', ...(token ? {Authorization: 'Bearer ' + token} : {}), ...(idempotencyKey ? {'Idempotency-Key': idempotencyKey} : {})},
    ...(body === undefined ? {} : {body: JSON.stringify(body)}),
  }).catch(() => {throw new Error('Não foi possível completar a operação. Confira sua conexão e os dados informados.');});
  if (response.status === 401) logout();
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(typeof data?.detail === 'string' ? data.detail : 'Não foi possível completar a operação. Confira sua conexão e os dados informados.');
    error.status = response.status; throw error;
  }
  return data;
}
function logout() {
  stopEvents();
  caixaUI.setUser(null);
  pendingSale = null; currentUserId = '';
  lastSale = null; lastHistory = null;
  syncPending = false;
  hideSaleToast();
  token = '';
  sessionStorage.removeItem('caixa-token');
  cart.clear(); products = [];
  historySnapshot = '';
  historyRequest++;
  historyPage = 1; historyTotal = 0; historyMarket = ''; historyLoading = false;
  clearTimeout(historySearchTimer);
  $('history-product').value = ''; $('history-quantity').value = ''; $('history-order').value = 'recent';
  $('password').value = '';
  $('workspace').hidden = true;
  $('login-panel').hidden = false;
  $('receipt').hidden = true;
}
function render() {
  const term = $('search').value.toLocaleLowerCase('pt-BR');
  $('products').replaceChildren();
  const filtered = products.filter(p => `${p.name} ${p.category_name || ''}`.toLocaleLowerCase('pt-BR').includes(term));
  if (!filtered.length) $('products').append(el('p', products.length ? tr('Nenhum produto encontrado.') : tr('Cadastre produtos e estoque neste mercado pelo Reponto para começar.')));
  for (const p of filtered) {
    const card = el('article', undefined, 'product');
    card.append(el('span', p.category_name || tr('Produto'), 'category'), el('h3', p.name), el('small', tr('{quantity} em estoque', {quantity: quantityWithUnit(p.stock, p.unit)})), el('strong', money(p.price)));
    const button = el('button', tr(Number(p.stock) <= 0 ? 'Sem estoque' : 'Adicionar +'), Number(p.stock) <= 0 ? 'out-of-stock' : undefined);
    button.disabled = busy || loading || !!pendingSale || Number(p.stock) - (cart.get(p.id) || 0) < (isCountUnit(p.unit) ? 1 : 0.001);
    button.onclick = () => {
      const available = Math.round((Number(p.stock) - (cart.get(p.id) || 0)) * 1000) / 1000;
      cart.set(p.id, Math.round(((cart.get(p.id) || 0) + Math.min(1, available)) * 1000) / 1000);
      render();
    };
    card.append(button); $('products').append(card);
  }
  $('cart').replaceChildren();
  if (!cart.size) $('cart').append(el('p', tr('Adicione produtos para iniciar uma venda.')));
  let total = 0;
  for (const [id, qty] of cart) {
    const p = products.find(p => p.id === id);
    if (!p) continue;
    const row = el('div', undefined, 'cart-item');
    row.append(el('h3', p.name));
    const controls = el('div', undefined, 'cart-controls');
    const input = el('input');
    input.type = 'number'; input.min = isCountUnit(p.unit) ? '1' : '0'; input.step = ['kg', 'l'].includes((p.unit || 'unidade').toLowerCase()) ? '0.1' : '1'; input.max = p.stock; input.value = qty;
    input.disabled = busy || loading || !!pendingSale; input.setAttribute('aria-label', tr('Quantidade de {name}', {name: p.name}));
    input.onchange = () => {
      const value = Number(input.value);
      if (isCountUnit(p.unit) && !Number.isInteger(value)) {
        message("Este produto deve ser vendido em quantidades inteiras.", true);
      } else if (!Number.isFinite(value) || value <= 0 || value > Number(p.stock) || Math.abs(value * 1000 - Math.round(value * 1000)) > 0.000001) {
        message('Informe uma quantidade positiva, com até três casas decimais, dentro do estoque disponível.', true);
      } else { cart.set(id, value); message(''); }
      render();
    };
    const remove = el('button', tr('Remover'), 'secondary');
    remove.disabled = busy || loading || !!pendingSale;
    remove.onclick = () => {cart.delete(id); render();};
    const subtotal = Math.round((Number(p.price) * qty + Number.EPSILON) * 100) / 100;
    total += subtotal;
    controls.append(input, remove, el('strong', money(subtotal))); row.append(controls); $('cart').append(row);
  }
  $('total').textContent = money(total);
  $('checkout').disabled = (!cart.size && !pendingSale) || busy || loading;
  $('clear').disabled = !cart.size || busy || loading || !!pendingSale;
  for (const id of ['market', 'logout']) $(id).disabled = busy || loading || (id === 'market' && !!pendingSale);
  $('market').disabled ||= !$('market').value;
  $('checkout').textContent = busy ? tr('Registrando venda…') : pendingSale ? tr('Confirmar venda pendente →') : tr('Concluir venda →');
}
async function loadHistory() {
  const market = $('market').value;
  if (historyMarket !== market) {historyMarket = market; historyPage = 1;}
  const version = ++historyRequest;
  if (!market) {historyLoading = false; $('history-error').hidden = true; renderHistory({items: [], total: 0, page: 1}); return;}
  if (!validHistoryQuantity()) {
    historyLoading = false; historySnapshot = '';
    $('history').replaceChildren();
    historyErrorKey = 'Informe uma quantidade positiva com até três casas decimais.';
    $('history-error').textContent = tr(historyErrorKey);
    $('history-error').hidden = false;
    updateHistoryControls();
    return;
  }
  const session = token;
  const key = historyKey();
  const params = new URLSearchParams({market_id: market, page: historyPage, page_size: HISTORY_PAGE_SIZE, order: $('history-order').value || 'recent'});
  if ($('history-product').value.trim()) params.set('product', $('history-product').value.trim());
  if ($('history-quantity').value) params.set('quantity', $('history-quantity').value);
  historyLoading = true;
  $('history-error').hidden = true;
  updateHistoryControls();
  try {
    const data = await api('/sales/history?' + params);
    if (version !== historyRequest || token !== session || key !== historyKey()) return;
    renderHistory(data);
  } catch (error) {
    if (version === historyRequest && token === session && key === historyKey()) {
      historyErrorKey = error.message;
      $('history-error').textContent = tr(historyErrorKey);
      $('history-error').hidden = false;
      // Evita exibir resultados de um filtro anterior como se fossem os atuais.
      $('history').replaceChildren();
      historySnapshot = '';
    }
  } finally {
    if (version === historyRequest) {historyLoading = false; updateHistoryControls();}
  }
}
function historyKey() {
  return JSON.stringify([$('market').value, $('history-product').value, $('history-quantity').value, $('history-order').value, historyPage]);
}
function updateHistoryControls() {
  const pages = Math.max(1, Math.ceil(historyTotal / HISTORY_PAGE_SIZE));
  const invalid = !validHistoryQuantity();
  $('history-prev').disabled = historyLoading || invalid || historyPage <= 1;
  $('history-next').disabled = historyLoading || invalid || historyPage >= pages;
  $('history-page').textContent = tr('Página {page} de {pages}', {page: historyPage, pages});
  const first = historyTotal ? (historyPage - 1) * HISTORY_PAGE_SIZE + 1 : 0;
  const last = Math.min(historyPage * HISTORY_PAGE_SIZE, historyTotal);
  $('history-count').textContent = historyLoading ? tr('Carregando vendas…') : tr('{first}–{last} de {total} vendas', {first, last, total: historyTotal});
  $('history').setAttribute('aria-busy', String(historyLoading));
}
function renderHistory(data) {
  lastHistory = data;
  historyPage = data.page;
  historyTotal = data.total;
  updateHistoryControls();
  lastHistoryKey = historyKey();
  const snapshot = JSON.stringify([caixaUI.locale, lastHistoryKey, data]);
  if (snapshot === historySnapshot) return;
  historySnapshot = snapshot;
  const sales = data.items;
  $('history').replaceChildren();
  if (!sales.length) $('history').append(el('p', $('history-product').value || $('history-quantity').value ? tr('Nenhuma venda encontrada com esses filtros.') : tr('Este mercado ainda não tem vendas.')));
  for (const sale of sales) {
    const row = el('div', undefined, 'history-row');
    const info = el('div');
    info.append(el('span', `${new Date(sale.sold_at).toLocaleString(caixaUI.formatLocale, {timeZone: 'America/Sao_Paulo'})} · ${sale.status === 'completed' ? tr('Concluída') : tr('Cancelada')}`));
    for (const item of sale.items) {
      info.append(el('small', tr('{name} · Quantidade: {quantity}', {name: item.product_name, quantity: quantityWithUnit(item.quantity, item.unit)})));
    }
    row.append(info, el('strong', money(sale.total))); $('history').append(row);
  }
}
async function loadProducts() {
  loading = true; render();
  try {
    products = $('market').value ? await api('/markets/' + encodeURIComponent($('market').value) + '/products') : [];
    reconcileCart();
    await loadHistory();
  } finally {loading = false; render(); flushSync();}
}
async function start() {
  const session = token;
  const [markets, user] = await Promise.all([api('/markets'), api('/auth/me')]);
  if (token !== session) return;
  caixaUI.setUser(user);
  currentUserId = user.id;
  try {
    const saved = JSON.parse(sessionStorage.getItem('caixa-pending-sale') || 'null');
    if (saved?.userId === user.id && saved?.key && saved?.body?.items?.length) pendingSale = saved;
  } catch {}

  updateMarkets(markets);
  if (pendingSale) {
    $('market').value = pendingSale.body.market_id;
    cart = new Map(pendingSale.body.items.map(item => [item.product_id, item.quantity]));
    message('Há uma venda pendente de confirmação. Clique em Confirmar venda pendente para consultar ou concluir a mesma tentativa, sem duplicá-la.', true);
  }
  $('login-panel').hidden = true; $('workspace').hidden = false;
  await loadProducts();
  void startEvents();
}

function canSync() {
  return token && !busy && !loading && !document.hidden &&
    !document.activeElement?.closest('#cart, #market');
}
async function syncData() {
  if (syncing || !canSync()) {syncPending = true; return;}
  syncing = true;
  syncPending = false;
  let succeeded = false;
  const session = token;
  const selected = $('market').value;
  try {
    const markets = await api('/markets');
    const next = markets.some(m => m.id === selected) ? selected : (markets[0]?.id || '');
    const freshProducts = next ? await api('/markets/' + encodeURIComponent(next) + '/products') : [];
    // A consulta não deve sobrescrever uma troca de mercado, sessão ou edição.
    if (token !== session) return;
    if ($('market').value !== selected || !canSync()) {syncPending = true; return;}
    const marketChanged = updateMarkets(markets);
    const productsChanged = JSON.stringify(products) !== JSON.stringify(freshProducts);
    if (marketChanged || productsChanged) {
      products = freshProducts;
      reconcileCart();
      render();
    }
    await loadHistory();
    succeeded = true;
  } catch {
    syncPending = true;
    if (token === session) {
      stopEvents();
      reconnectTimer = setTimeout(startEvents, 3000);
    }
  } finally {
    syncing = false;
    if (succeeded) flushSync();
  }
}
window.addEventListener('focus', requestSync);
window.addEventListener('online', () => {stopEvents(); void startEvents(); requestSync();});
document.addEventListener('visibilitychange', () => {if (!document.hidden) requestSync();});
document.addEventListener('focusout', () => {setTimeout(flushSync, 0);});
$('login-form').onsubmit = async (event) => {
  event.preventDefault(); $('login-button').disabled = true; message('');
  try {
    const data = await api('/auth/login', {email: $('email').value.trim(), password: $('password').value});
    token = data.access_token; sessionStorage.setItem('caixa-token', token); $('password').value = '';
    await start();
  } catch (error) {message(error.message, true);}
  finally {$('login-button').disabled = false;}
};
$('reponto-link').onclick = () => {const url = new URL('/dashboard', window.location.href); url.port = '3300'; window.location.assign(url.href);};
$('logout').onclick = () => {logout(); message('');};
$('search').oninput = render;
function searchHistory() {
  clearTimeout(historySearchTimer);
  historyRequest++;
  historyPage = 1;
  if (!validHistoryQuantity()) {
    void loadHistory();
    return;
  }
  historyLoading = true;
  updateHistoryControls();
  historySearchTimer = setTimeout(() => {void loadHistory();}, 250);
}
$('history-product').oninput = searchHistory;
$('history-quantity').oninput = searchHistory;
$('history-order').onchange = () => {clearTimeout(historySearchTimer); historyPage = 1; void loadHistory();};
$('history-clear').onclick = () => {
  clearTimeout(historySearchTimer);
  $('history-product').value = ''; $('history-quantity').value = ''; $('history-order').value = 'recent';
  historyPage = 1;
  void loadHistory();
};
$('history-prev').onclick = () => {if (!historyLoading && historyPage > 1) {historyPage--; void loadHistory();}};
$('history-next').onclick = () => {if (!historyLoading && historyPage * HISTORY_PAGE_SIZE < historyTotal) {historyPage++; void loadHistory();}};
$('clear').onclick = () => {cart.clear(); render();};
$('market').onchange = () => {cart.clear(); $('receipt').hidden = true; message(''); loadProducts().catch(e => message(e.message, true));};
$('checkout').onclick = async () => {
  if (busy || loading || (!cart.size && !pendingSale)) return;
  busy = true; render(); message('');
  try {
    if (!pendingSale) savePending({key: crypto.randomUUID(), userId: currentUserId,
      body: {market_id: $('market').value, items: [...cart].map(([product_id, quantity]) => ({product_id, quantity}))}});
    const sale = await api('/sales', pendingSale.body, pendingSale.key);
    savePending(null);
    cart.clear();
    lastSale = sale;
    renderReceipt(sale);
    $('receipt').hidden = false;
    if (sale.status === 'cancelled') message('Esta venda já foi registrada e cancelada. Nenhuma nova venda foi criada.', true);
    else showSaleToast();
    try {await loadProducts();} catch {message('Venda gravada. A atualização da tela será tentada novamente automaticamente.', true); requestSync();}
  } catch (error) {
    if (error.status >= 400 && error.status < 500 && ![401, 408, 409, 429].includes(error.status)) savePending(null);
    message(pendingSale ? '{error} Clique em Confirmar venda pendente para repetir a mesma tentativa com segurança.' : '{error}', true, {error: error.message});
  } finally {busy = false; render(); flushSync();}
};

function renderReceipt(sale) {
  $('receipt').replaceChildren(el('span', tr(sale.status === 'cancelled' ? 'VENDA CANCELADA' : 'VENDA CONCLUÍDA'), 'eyebrow'), el('h2', tr('{total} registrado no Reponto', {total: money(sale.total)})), el('p', tr('ID da venda: {id}', {id: sale.id})));
  for (const item of sale.items) $('receipt').append(el('p', `${item.product_name} · ${quantityWithUnit(item.quantity, item.unit)} × ${money(item.unit_price)} = ${money(item.subtotal)}`));
}
window.addEventListener('caixa:locale', () => {
  render();
  if (lastHistory && lastHistoryKey === historyKey()) renderHistory(lastHistory);
  else updateHistoryControls();
  if (lastSale && !$('receipt').hidden) renderReceipt(lastSale);
  if (lastMessage) message(lastMessage.key, lastMessage.error, lastMessage.values);
  if (!$('history-error').hidden && historyErrorKey) $('history-error').textContent = tr(historyErrorKey);
  if (!$('market').value && $('market').options[0]) $('market').options[0].textContent = tr('Nenhum mercado cadastrado');
});

if (token) start().catch(e => {logout(); message(e.message, true);});
