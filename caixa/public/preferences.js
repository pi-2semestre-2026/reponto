/* Preferences use the same names, languages and theme palette as Reponto. */
const caixaUI = (() => {
  const english = {
    'Caixa • Simulador de mercado': 'Checkout • Market simulator',
    'SIMULADOR DE MERCADO': 'MARKET SIMULATOR', 'Caixa': 'Checkout',
    'Integrado ao Reponto': 'Connected to Reponto', 'Idioma': 'Language',
    'Ativar modo claro': 'Switch to light mode', 'Ativar modo escuro': 'Switch to dark mode',
    'Conta de {name}': 'Account for {name}', 'Sair': 'Sign out',
    'ABERTURA DO CAIXA': 'OPEN CHECKOUT', 'Vamos começar?': 'Ready to start?',
    'Entre com sua conta do Reponto para vender os produtos dos seus mercados.': 'Sign in with your Reponto account to sell products from your stores.',
    'E-mail': 'Email', 'Senha': 'Password', 'Abrir caixa →': 'Open checkout →',
    'As vendas realizadas aqui gravam dados e movimentam o estoque do Reponto.': 'Sales made here are saved and update stock in Reponto.',
    'Cadastre um mercado e seus produtos no Reponto. Eles aparecerão aqui automaticamente.': 'Register a store and its products in Reponto. They will appear here automatically.',
    'Mercado': 'Store', 'Atualizar produtos': 'Refresh products',
    'PRODUTOS PRÉ-CADASTRADOS': 'REGISTERED PRODUCTS', 'O que vai levar?': 'What would you like?',
    'Buscar produto': 'Search products', 'Digite o nome ou a categoria': 'Enter a name or category',
    'VENDA EM ANDAMENTO': 'CURRENT SALE', 'Seu carrinho': 'Your cart', 'Total estimado': 'Estimated total',
    'O preço e o estoque são conferidos pelo Reponto ao finalizar.': 'Reponto checks prices and stock at checkout.',
    'Concluir venda →': 'Complete sale →', 'Limpar carrinho': 'Clear cart',
    'CONFERÊNCIA': 'SALES HISTORY', 'Últimas vendas do mercado': 'Latest store sales',
    'Vendas feitas em todas as telas do Reponto.': 'Sales made across all Reponto screens.',
    'Nome do produto': 'Product name', 'Buscar produto vendido': 'Search sold products',
    'Quantidade vendida do produto': 'Product quantity sold', 'Qualquer quantidade': 'Any quantity',
    'Ordenar por': 'Sort by', 'Mais recentes': 'Most recent',
    'Maior valor de venda': 'Highest sale value', 'Menor valor de venda': 'Lowest sale value',
    'Maior quantidade total': 'Highest total quantity', 'Menor quantidade total': 'Lowest total quantity',
    'Limpar filtros': 'Clear filters',
    'A quantidade busca um item da venda. A ordenação considera o valor ou a quantidade total da venda.': 'Quantity matches an item in the sale. Sorting uses the total sale value or quantity.',
    'Páginas do histórico de vendas': 'Sales history pages', '← Anterior': '← Previous', 'Próxima →': 'Next →',
    'Página {page} de {pages}': 'Page {page} of {pages}', 'Venda gravada': 'Sale saved',
    'Caixa de testes · Os dados são reais no banco conectado ao Reponto.': 'Test checkout · Changes affect the database connected to Reponto.',
    'Sua sessão expirou. Entre novamente.': 'Your session expired. Please sign in again.',
    'Nenhum mercado cadastrado': 'No stores registered',
    'Alguns itens foram removidos do carrinho porque o produto ou o estoque disponível mudou.': 'Some items were removed from your cart because the product or its available stock changed.',
    'Não foi possível completar a operação. Confira sua conexão e os dados informados.': 'Unable to complete the operation. Check your connection and the information provided.',
    'Nenhum produto encontrado.': 'No products found.',
    'Cadastre produtos e estoque neste mercado pelo Reponto para começar.': 'Register products and stock for this store in Reponto to get started.',
    'Produto': 'Product', '{quantity} em estoque': '{quantity} in stock', 'Adicionar +': 'Add +',
    'Adicione produtos para iniciar uma venda.': 'Add products to start a sale.',
    'Quantidade de {name}': 'Quantity of {name}',
    'Informe uma quantidade positiva, com até três casas decimais, dentro do estoque disponível.': 'Enter a positive quantity with up to three decimal places, within the available stock.',
    'Remover': 'Remove', 'Registrando venda…': 'Saving sale…',
    'Informe uma quantidade positiva com até três casas decimais.': 'Enter a positive quantity with up to three decimal places.',
    'Este produto deve ser vendido em quantidades inteiras.': 'This product must be sold in whole quantities.',
    'VENDA CANCELADA': 'SALE CANCELLED',
    'Esta venda já foi registrada e cancelada. Nenhuma nova venda foi criada.': 'This sale was already saved and cancelled. No new sale was created.',
    'Confirmar venda pendente →': 'Confirm pending sale →',
    'Há uma venda pendente de confirmação. Clique em Confirmar venda pendente para consultar ou concluir a mesma tentativa, sem duplicá-la.': 'A sale is awaiting confirmation. Click Confirm pending sale to retrieve or complete the same attempt without duplicating it.',
    '{error} Clique em Confirmar venda pendente para repetir a mesma tentativa com segurança.': '{error} Click Confirm pending sale to retry the same attempt safely.',
    'Esta tentativa de venda já foi usada com outros itens': 'This sale attempt has already been used with other items',
    'Carregando vendas…': 'Loading sales…', '{first}–{last} de {total} vendas': '{first}–{last} of {total} sales',
    'Nenhuma venda encontrada com esses filtros.': 'No sales match these filters.',
    'Este mercado ainda não tem vendas.': 'This store has no sales yet.',
    'Concluída': 'Completed', 'Cancelada': 'Cancelled',
    '{name} · Quantidade: {quantity}': '{name} · Quantity: {quantity}',
    'VENDA CONCLUÍDA': 'SALE COMPLETED', '{total} registrado no Reponto': '{total} saved in Reponto',
    'ID da venda: {id}': 'Sale ID: {id}',
    'Venda gravada, mas a atualização da tela falhou. Clique em Atualizar produtos.': 'Sale saved, but the screen could not refresh. Click Refresh products.',
    '{error} Se houve falha de conexão, consulte as últimas vendas antes de tentar novamente para evitar duplicidade.': '{error} If the connection failed, check the latest sales before trying again to avoid duplicates.',
    'E-mail ou senha incorretos': 'Incorrect email or password', 'Não autenticado': 'Not authenticated',
    'Token inválido ou expirado': 'Invalid or expired token',
    'Produto não encontrado neste mercado': 'Product not found in this store',
    'Mercado não encontrado': 'Store not found', 'Usuário não encontrado': 'User not found',
  };
  const read = (key, fallback) => {try {return localStorage.getItem(key) || fallback;} catch {return fallback;}};
  const write = (key, value) => {try {localStorage.setItem(key, value);} catch {}};
  let locale = read('pm_locale', 'pt') === 'en' ? 'en' : 'pt';
  let theme = read('theme', 'light') === 'dark' ? 'dark' : 'light';
  let user = null;
  const t = (key, values = {}) => {
    const translated = Object.prototype.hasOwnProperty.call(english, key) ? english[key] : null;
    let text = locale === 'en' && translated ? translated : key;
    if (locale === 'en' && !translated) text = text.replace(/^Estoque insuficiente para (.+): (.+) disponível$/, 'Insufficient stock for $1: $2 available');
    return text.replace(/\{(\w+)\}/g, (match, name) => values[name] ?? match);
  };
  function account() {
    const menu = document.getElementById('account-menu');
    menu.hidden = !user;
    if (!user) {menu.open = false; return;}
    document.getElementById('user-name').textContent = user.name;
    document.getElementById('user-initial').textContent = Array.from(user.name.trim())[0]?.toLocaleUpperCase() || '?';
    document.getElementById('user-email').textContent = user.email;
    document.getElementById('account-trigger').setAttribute('aria-label', t('Conta de {name}', {name: user.name}));
  }
  function applyTheme() {
    document.documentElement.dataset.theme = theme;
    const label = t(theme === 'dark' ? 'Ativar modo claro' : 'Ativar modo escuro');
    document.getElementById('theme-toggle').title = label;
    document.getElementById('theme-toggle').setAttribute('aria-label', label);
    document.getElementById('theme-sun').toggleAttribute('hidden', theme !== 'dark');
    document.getElementById('theme-moon').toggleAttribute('hidden', theme === 'dark');
  }
  function apply() {
    document.documentElement.lang = locale === 'pt' ? 'pt-BR' : 'en';
    document.title = t('Caixa • Simulador de mercado');
    document.querySelectorAll('[data-i18n]').forEach(node => {node.textContent = t(node.dataset.i18n);});
    for (const [data, attr] of [['i18nPlaceholder', 'placeholder'], ['i18nAria', 'aria-label'], ['i18nTitle', 'title']]) {
      document.querySelectorAll(`[data-${data.replace(/[A-Z]/g, c => '-' + c.toLowerCase())}]`).forEach(node => node.setAttribute(attr, t(node.dataset[data])));
    }
    document.querySelectorAll('[data-locale]').forEach(node => {
      node.setAttribute('aria-pressed', String(node.dataset.locale === locale));
    });
    applyTheme(); account();
  }
  const setLocale = value => {
    if (!['pt', 'en'].includes(value)) return;
    locale = value; write('pm_locale', locale); apply();
    document.getElementById('language-menu').open = false;
    window.dispatchEvent(new Event('caixa:locale'));
  };
  const setTheme = value => {theme = value === 'dark' ? 'dark' : 'light'; write('theme', theme); applyTheme();};
  document.getElementById('theme-toggle').onclick = () => setTheme(theme === 'dark' ? 'light' : 'dark');
  document.querySelectorAll('[data-locale]').forEach(node => {node.onclick = () => setLocale(node.dataset.locale);});
  document.addEventListener('click', event => {
    for (const id of ['language-menu', 'account-menu']) {
      const menu = document.getElementById(id);
      if (!menu.contains(event.target)) menu.open = false;
    }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') for (const id of ['language-menu', 'account-menu']) document.getElementById(id).open = false;
  });
  apply();
  return {t, setLocale, setTheme, setUser(value) {user = value; account();},
    get locale() {return locale;}, get formatLocale() {return locale === 'pt' ? 'pt-BR' : 'en-US';}, get theme() {return theme;}};
})();
