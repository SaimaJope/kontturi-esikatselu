import { people, offices, site } from './site-data.js?v=20260910-premium';

const backToTop = document.querySelector('.back-to-top');
if (backToTop) {
  const scrollPosition = () => Math.max(0, Math.min(window.scrollY, document.documentElement.scrollHeight - window.innerHeight));
  let previousScrollY = scrollPosition();
  let direction = 0;
  let distance = 0;
  let scheduled = false;
  let visible;
  const showBackToTop = next => {
    if (visible === next) return;
    visible = next;
    backToTop.classList.toggle('is-visible', next);
    backToTop.inert = !next;
    backToTop.setAttribute('aria-hidden', String(!next));
    backToTop.tabIndex = next ? 0 : -1;
  };
  const updateBackToTop = () => {
    scheduled = false;
    const y = scrollPosition();
    const delta = y - previousScrollY;
    previousScrollY = y;
    if (y < 300) {
      direction = 0;
      distance = 0;
      showBackToTop(false);
      return;
    }
    if (!delta) return;
    const nextDirection = Math.sign(delta);
    if (nextDirection !== direction) {
      direction = nextDirection;
      distance = 0;
    }
    distance += Math.abs(delta);
    // Hide promptly on an intentional upward scroll; ignore trackpad jitter.
    if (direction < 0 && distance >= 6) showBackToTop(false);
    else if (direction > 0 && distance >= 24) showBackToTop(true);
  };
  const resetBackToTop = () => {
    previousScrollY = scrollPosition();
    direction = 0;
    distance = 0;
    showBackToTop(previousScrollY >= 300);
  };
  window.addEventListener('scroll', () => {
    if (!scheduled) {
      scheduled = true;
      requestAnimationFrame(updateBackToTop);
    }
  }, { passive: true });
  window.addEventListener('pageshow', resetBackToTop);
  resetBackToTop();
  // Keep the element rendered so CSS can finish (or reverse) the fade.
  backToTop.hidden = false;
}

const menu = document.querySelector('#mobile-navigation');
if (menu) {
  menu.addEventListener('click', event => { if (event.target.closest('a')) menu.open = false; });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && menu.open) { menu.open = false; menu.querySelector('summary').focus(); }
  });
  document.addEventListener('click', event => { if (menu.open && !menu.contains(event.target)) menu.open = false; });
  matchMedia('(min-width: 1001px)').addEventListener('change', event => { if (event.matches) menu.open = false; });
}
const search = document.querySelector('#person-search');
const peopleCards = document.querySelector('#people-cards');
if (peopleCards) {
  const cards = [...peopleCards.querySelectorAll('.person-card')];
  const controls = document.querySelector('.people-controls');
  const previous = controls.querySelector('.people-previous');
  const next = controls.querySelector('.people-next');
  const range = document.querySelector('#people-range');
  const mobile = matchMedia('(max-width: 700px)');
  const pageSize = () => mobile.matches ? 1 : 3;
  const remembered = Number.isInteger(history.state?.peopleStart) ? history.state.peopleStart : 0;
  let start = Math.floor(Math.max(0, Math.min(remembered, cards.length - 1)) / pageSize()) * pageSize();
  function showPeople() {
    const size = pageSize();
    const end = Math.min(start + size, cards.length);
    cards.forEach((card, index) => { card.hidden = index < start || index >= end; });
    previous.disabled = start === 0;
    next.disabled = end === cards.length;
    range.textContent = (size === 1 ? String(start + 1) : `${start + 1}–${end}`) + ` / ${cards.length}`;
    range.setAttribute('aria-label', `Näytetään asiantuntijat ${start + 1}–${end}, yhteensä ${cards.length}`);
    // Keep the current group when returning from an expert profile.
    history.replaceState({ ...history.state, peopleStart: start }, '');
  }
  function move(direction) {
    const size = pageSize();
    const lastPage = Math.floor((cards.length - 1) / size) * size;
    start = Math.max(0, Math.min(start + direction * size, lastPage));
    showPeople();
  }
  previous.addEventListener('click', () => move(-1));
  next.addEventListener('click', () => move(1));
  mobile.addEventListener('change', () => {
    start = Math.floor(start / pageSize()) * pageSize();
    showPeople();
  });
  controls.hidden = false;
  showPeople();
}
if (search) {
  const cards = [...document.querySelectorAll('[data-person-name]')];
  const count = document.querySelector('#search-count');
  const clear = document.querySelector('#clear-search');
  const grid = document.querySelector('.directory-grid');
  const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('fi').trim().replace(/\s+/g, ' ');
  function filterPeople(updateURL = true) {
    const terms = normalize(search.value).split(' ').filter(Boolean);
    let total = 0;
    cards.forEach(card => {
      card.hidden = !terms.every(term => normalize(card.dataset.personName).includes(term));
      if (!card.hidden) total++;
    });
    grid.hidden = total === 0;
    document.querySelector('#search-empty').hidden = total !== 0;
    count.textContent = total + (total === 1 ? ' henkilö' : ' henkilöä');
    clear.hidden = search.value.length === 0;
    if (updateURL) {
      const url = new URL(location.href);
      if (search.value.trim()) url.searchParams.set('q', search.value.trim());
      else url.searchParams.delete('q');
      history.replaceState(history.state, '', url);
    }
  }
  search.addEventListener('input', () => filterPeople());
  clear.addEventListener('click', () => { search.value = ''; filterPeople(); search.focus(); });
  function readSearch() { search.value = new URLSearchParams(location.search).get('q') || ''; filterPeople(false); }
  addEventListener('popstate', readSearch);
  addEventListener('pageshow', readSearch);
  search.disabled = false;
  readSearch();
}
const form = document.querySelector('#contact-form');
const serviceSearch = document.querySelector('#service-search');
if (serviceSearch) {
  const rows = [...document.querySelectorAll('.practice-row')];
  const count = document.querySelector('#service-count');
  const clear = document.querySelector('#clear-service-search');
  const normalize = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('fi');
  function filterServices() {
    const terms = normalize(serviceSearch.value).trim().split(/\s+/).filter(Boolean);
    let visible = 0;
    rows.forEach(row => {
      row.hidden = !terms.every(term => normalize(row.textContent).includes(term));
      if (!row.hidden) visible++;
    });
    count.textContent = visible + (visible === 1 ? ' palvelu' : ' palvelua');
    document.querySelector('#service-empty').hidden = visible !== 0;
    clear.hidden = serviceSearch.value.length === 0;
  }
  serviceSearch.addEventListener('input', filterServices);
  clear.addEventListener('click', () => { serviceSearch.value = ''; filterServices(); serviceSearch.focus(); });
  addEventListener('pageshow', filterServices);
  serviceSearch.disabled = false;
  filterServices();
}
if (form) {
  const byId = id => document.getElementById(id);
  const personSelect = byId('person'), topicSelect = byId('topic'), officeSelect = byId('office');
  const formView = byId('form-view'), receipt = byId('receipt-view'), errorSummary = byId('form-error-summary');
  const requiredIds = ['topic', 'message', 'name', 'email'];
  const selectedPerson = () => people.find(person => person.id === personSelect.value);
  const selectedOffice = () => offices.find(office => office.id === officeSelect.value);
  let previousSuggestedTopic = '';
  let draft = null;
  const draftFields = ['name', 'email', 'phone', 'message'];
  const rememberDraft = () => { draft = Object.fromEntries(draftFields.map(id => [id, byId(id).value])); };
  form.addEventListener('input', rememberDraft);
  function updateDirectContact() {
    const person = selectedPerson(), office = selectedOffice();
    byId('direct-label').textContent = person ? 'Valitsemasi asiantuntija' : 'Toimiston yhteystiedot';
    byId('direct-name').textContent = person?.name || (office ? 'Kontturi & Co · ' + office.name : 'Kontturi & Co');
    byId('direct-role').textContent = person?.role || office?.hours || '';
    byId('direct-role').hidden = !person && !office;
    byId('direct-phone').textContent = person?.phone || office?.phone || offices[0].phone;
    byId('direct-phone').href = 'tel:' + (person?.tel || office?.tel || offices[0].tel);
    byId('direct-email').textContent = person?.email || site.email;
    byId('direct-email').href = 'mailto:' + (person?.email || site.email);
    byId('quick-phone').href = byId('direct-phone').href;
    byId('quick-email').href = byId('direct-email').href;
    byId('form-recipient').hidden = !person && !office;
    byId('form-recipient').textContent = 'Yhteydenotto: ' + [person?.name, office?.name].filter(Boolean).join(' · ');
    const portrait = byId('direct-portrait');
    portrait.hidden = !person?.image;
    if (person?.image) portrait.src = 'assets/' + person.image + '.webp';
    else portrait.removeAttribute('src');
    byId('routing-summary').textContent = [person?.name, office?.name].filter(Boolean).join(' · ') || 'Autamme löytämään sopivan asiantuntijan.';
    const link = byId('direct-profile');
    link.href = person?.slug ? person.slug + '.html' : 'asiantuntijat.html';
    link.firstChild.textContent = person?.slug ? 'Tutustu asiantuntijaan ' : 'Asiantuntijoiden yhteystiedot ';
  }
  function writeSelection() {
    const url = new URL(location.href);
    // Only public routing identifiers enter the URL, never form contents.
    [['henkilo', personSelect.value], ['aihe', topicSelect.value], ['toimipaikka', officeSelect.value === 'any' ? '' : officeSelect.value]].forEach(([key, value]) => {
      if (value) url.searchParams.set(key, value); else url.searchParams.delete(key);
    });
    history.replaceState({ ...history.state, contactPreview: false }, '', url);
  }
  function readSelection() {
    const params = new URLSearchParams(location.search);
    const person = people.find(person => person.id === params.get('henkilo'));
    personSelect.value = person?.id || '';
    const topic = params.get('aihe') || person?.topic || '';
    topicSelect.value = [...topicSelect.options].some(option => option.value === topic) ? topic : '';
    officeSelect.value = offices.some(office => office.id === params.get('toimipaikka')) ? params.get('toimipaikka') : 'any';
    previousSuggestedTopic = person?.topic || '';
    updateDirectContact();
  }
  personSelect.addEventListener('change', () => {
    const person = selectedPerson();
    if (person?.topic && (!topicSelect.value || topicSelect.value === previousSuggestedTopic)) topicSelect.value = person.topic;
    previousSuggestedTopic = person?.topic || '';
    updateDirectContact(); writeSelection();
  });
  officeSelect.addEventListener('change', () => { updateDirectContact(); writeSelection(); });
  topicSelect.addEventListener('change', () => { previousSuggestedTopic = ''; writeSelection(); });
  function validateField(id) {
    const input = byId(id);
    let message = '';
    if (!input.value.trim()) message = { name: 'Kirjoita nimesi.', email: 'Kirjoita sähköpostiosoitteesi.', topic: 'Valitse aihe tai ”Muu asia / en ole varma”.', message: 'Kirjoita lyhyt kuvaus asiasta.' }[id];
    else if (id === 'email' && !input.validity.valid) message = 'Tarkista sähköpostiosoite, esimerkiksi nimi@esimerkki.fi.';
    byId(id + '-error').textContent = message;
    if (message) input.setAttribute('aria-invalid', 'true'); else input.removeAttribute('aria-invalid');
    return !message;
  }
  requiredIds.forEach(id => {
    const input = byId(id);
    function revalidate() {
      if (input.hasAttribute('aria-invalid')) {
        validateField(id);
        if (!requiredIds.some(field => byId(field).getAttribute('aria-invalid') === 'true')) errorSummary.hidden = true;
      }
    }
    input.addEventListener('input', revalidate); input.addEventListener('change', revalidate);
  });
  function showForm(focus = false) {
    formView.hidden = false; receipt.hidden = true;
    // Some browsers restore form controls after popstate. Restore the in-memory draft after that step.
    requestAnimationFrame(() => {
      if (draft) draftFields.forEach(id => { byId(id).value = draft[id]; });
      if (focus) byId('name').focus({ preventScroll: true });
    });
  }
  function showReceipt(focus = false) {
    byId('receipt-person').textContent = selectedPerson()?.name || 'Kontturi & Co';
    byId('receipt-topic').textContent = topicSelect.selectedOptions[0]?.textContent || 'Ei valintaa';
    byId('receipt-office').textContent = selectedOffice()?.name || 'Mikä tahansa toimipaikka';
    for (const id of ['name', 'email', 'message']) byId('receipt-' + id).textContent = byId(id).value.trim();
    formView.hidden = true; receipt.hidden = false;
    if (focus) byId('receipt-title').focus();
  }
  // Attach prevention before enabling the demo. No network send or storage.
  form.addEventListener('submit', event => {
    event.preventDefault();
    const invalid = requiredIds.filter(id => !validateField(id));
    errorSummary.hidden = invalid.length === 0;
    if (invalid.length) {
      errorSummary.textContent = 'Tarkista ' + invalid.length + (invalid.length === 1 ? ' merkitty kenttä.' : ' merkittyä kenttää.');
      byId(invalid[0]).focus(); return;
    }
    rememberDraft();
    history.pushState({ ...history.state, contactPreview: true }, '', location.href);
    showReceipt(true);
  });
  byId('back-to-form').addEventListener('click', () => {
    if (history.state?.contactPreview) history.back(); else showForm(true);
  });
  addEventListener('popstate', () => { readSelection(); if (history.state?.contactPreview) showReceipt(true); else showForm(); });
  addEventListener('pageshow', () => {
    readSelection();
    if (history.state?.contactPreview && requiredIds.every(id => byId(id).value.trim())) showReceipt(); else showForm();
  });
  readSelection();
  byId('contact-fields').disabled = false;
}
