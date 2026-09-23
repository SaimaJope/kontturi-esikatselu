const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const capture = new URLSearchParams(location.search).has('design-capture');
// The office photograph is a preview treatment until dedicated footage is supplied.
// Never start continuous motion without a working pause control.
const heroMedia = document.querySelector('.hero-media');
const heroMotionToggle = heroMedia?.querySelector('.hero-motion-toggle');
if (heroMotionToggle) {
  const english = document.documentElement.lang === 'en';
  let paused = false;
  const updateHeroMotion = () => {
    const enabled = !reduced.matches && !capture;
    heroMotionToggle.hidden = !enabled;
    heroMedia.classList.toggle('is-animated', enabled);
    heroMedia.classList.toggle('is-paused', paused || document.hidden);
    heroMotionToggle.textContent = english
      ? (paused ? 'Resume image motion' : 'Pause image motion')
      : (paused ? 'Jatka kuvan liikettä' : 'Pysäytä kuvan liike');
  };
  heroMotionToggle.addEventListener('click', () => {
    paused = !paused;
    updateHeroMotion();
  });
  reduced.addEventListener('change', updateHeroMotion);
  document.addEventListener('visibilitychange', updateHeroMotion);
  updateHeroMotion();
}
const header = document.querySelector('.site-header');
let previousY = scrollY;
let scheduled = false;

if (header) {
  addEventListener('scroll', () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      const y = scrollY;
      header.classList.toggle('header-visible', y > 180 && y < previousY);
      previousY = y;
      scheduled = false;
    });
  }, { passive: true });
}

// Only enhance content after an observer exists. The document remains readable
// without JavaScript and when reduced motion is enabled.
if (!capture && !reduced.matches && 'IntersectionObserver' in window) {
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.08, rootMargin: '0px 0px -24px 0px' });
  const targets = document.querySelectorAll('.section-heading,.service-entry,.process-grid li,.office,.expertise-grid article,.profile-biography,.directory-help,.closing-copy,.closing-action,.editorial-split>div,.practice-row,.location-card,.partner-grid article,.article-body section');
  targets.forEach(target => {
    if (target.getBoundingClientRect().top < innerHeight) return;
    target.classList.add('reveal-pending');
    observer.observe(target);
  });
  reduced.addEventListener('change', event => {
    if (!event.matches) return;
    observer.disconnect();
    targets.forEach(target => target.classList.add('is-visible'));
  });
  addEventListener('beforeprint', () => targets.forEach(target => target.classList.add('is-visible')));
}

// Ambient motion is driven by the reader. Nothing loops while the page is idle.
// Keep the text stationary and move only the decorative light and brand mark.
if (!capture) {
  const surfaces = [...document.querySelectorAll('.brand-light')].map(light => ({
    light, surface: light.parentElement,
    mark: light.parentElement.querySelector('.hero-k,.closing-k'),
    x: 0, y: 0, targetX: 0, targetY: 0, pointerX: 0, pointerY: 0, active: false
  }));
  const finePointer = matchMedia('(hover: hover) and (pointer: fine)');
  let frameId = 0, scrollDirty = true, lastTime = 0;
  function wake() {
    if (!frameId && !reduced.matches && !document.hidden) frameId = requestAnimationFrame(tick);
  }
  function tick(time) {
    frameId = 0;
    if (reduced.matches || document.hidden) return;
    const smoothing = 1 - Math.exp(-Math.min(40, time - (lastTime || time - 16)) / 190);
    lastTime = time;
    let moving = false;
    for (const item of surfaces) {
      if (!item.active) continue;
      if (scrollDirty) {
        const box = item.surface.getBoundingClientRect();
        const progress = (innerHeight / 2 - box.top - box.height / 2) / (innerHeight + box.height);
        item.scrollY = Math.max(-22, Math.min(22, progress * 54));
      }
      item.targetX = item.pointerX;
      item.targetY = item.pointerY + (item.scrollY || 0);
      item.x += (item.targetX - item.x) * smoothing;
      item.y += (item.targetY - item.y) * smoothing;
      item.light.style.translate = `${item.x.toFixed(2)}px ${item.y.toFixed(2)}px`;
      if (item.mark) item.mark.style.translate = `${(item.x * .22).toFixed(2)}px ${(item.y * .48).toFixed(2)}px`;
      moving ||= Math.abs(item.targetX - item.x) + Math.abs(item.targetY - item.y) > .05;
    }
    scrollDirty = false;
    if (moving) wake();
  }
  const visibility = 'IntersectionObserver' in window ? new IntersectionObserver(entries => {
    for (const entry of entries) {
      const item = surfaces.find(s => s.surface === entry.target);
      if (item) item.active = entry.isIntersecting;
    }
    scrollDirty = true; wake();
  }, { rootMargin: '100px' }) : null;
  for (const item of surfaces) {
    if (visibility) visibility.observe(item.surface); else item.active = true;
    item.surface.addEventListener('pointermove', event => {
      if (reduced.matches || !finePointer.matches) return;
      const box = item.surface.getBoundingClientRect();
      item.pointerX = ((event.clientX - box.left) / box.width - .5) * 72;
      item.pointerY = ((event.clientY - box.top) / box.height - .5) * 44;
      wake();
    }, { passive: true });
    item.surface.addEventListener('pointerleave', () => {
      item.pointerX = 0; item.pointerY = 0; wake();
    }, { passive: true });
  }
  addEventListener('scroll', () => { scrollDirty = true; wake(); }, { passive: true });
  addEventListener('resize', () => { scrollDirty = true; wake(); }, { passive: true });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { cancelAnimationFrame(frameId); frameId = 0; }
    else { lastTime = 0; scrollDirty = true; wake(); }
  });
  reduced.addEventListener('change', () => {
    cancelAnimationFrame(frameId); frameId = 0;
    for (const item of surfaces) {
      item.x = item.y = 0;
      item.light.style.removeProperty('translate');
      item.mark?.style.removeProperty('translate');
    }
    if (!reduced.matches) { scrollDirty = true; wake(); }
  });
  wake();

  if (!reduced.matches && 'IntersectionObserver' in window) {
    const photos = document.querySelectorAll('.process-photo,.editorial-photo,.editorial-story figure');
    const photoObserver = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-visible'); photoObserver.unobserve(entry.target);
      });
    }, { threshold: .12 });
    photos.forEach(photo => {
      if (photo.getBoundingClientRect().top < innerHeight) return;
      photo.classList.add('photo-reveal'); photoObserver.observe(photo);
    });
    const showPhotos = () => photos.forEach(photo => photo.classList.add('is-visible'));
    reduced.addEventListener('change', event => { if (event.matches) { photoObserver.disconnect(); showPhotos(); } });
    addEventListener('beforeprint', showPhotos);
  }
}

document.querySelectorAll('.people-arrows button').forEach(button => {
  button.addEventListener('click', () => {
    if (reduced.matches || capture) return;
    document.querySelectorAll('#people-cards .person-card:not([hidden])').forEach((card, index) => {
      card.getAnimations().forEach(animation => animation.cancel());
      card.animate([{ opacity: 0, transform: 'translateY(14px)' }, { opacity: 1, transform: 'none' }], {
        duration: 480, delay: index * 55, easing: 'cubic-bezier(.22,1,.36,1)', fill: 'backwards'
      });
    });
  });
});
