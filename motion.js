const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const capture = new URLSearchParams(location.search).has('design-capture');
// The poster remains visible until video playback succeeds. Load no video for
// reduced motion, design captures or visitors without JavaScript.
const heroMedia = document.querySelector('.hero-media');
const heroVideo = heroMedia?.querySelector('video');
const heroMotionToggle = heroMedia?.querySelector('.hero-motion-toggle');
if (heroVideo && heroMotionToggle) {
  const english = document.documentElement.lang === 'en';
  let userPaused = false;
  let failed = false;
  let playRequest = 0;
  const updateControl = () => {
    heroMotionToggle.hidden = reduced.matches || capture || failed;
    heroMotionToggle.textContent = english
      ? (heroVideo.paused ? 'Play background video' : 'Pause background video')
      : (heroVideo.paused ? 'Toista taustavideo' : 'Pysäytä taustavideo');
  };
  const updateHeroMotion = () => {
    const request = ++playRequest;
    const staticOnly = reduced.matches || capture || failed;
    if (staticOnly || userPaused || document.hidden) {
      heroVideo.pause();
      if (staticOnly) heroMedia.classList.remove('is-playing');
      updateControl();
      return;
    }
    if (!heroVideo.getAttribute('src')) heroVideo.src = heroVideo.dataset.src;
    heroVideo.muted = true;
    heroVideo.play().catch(error => {
      if (request !== playRequest) return;
      heroVideo.pause();
      heroMedia.classList.remove('is-playing');
      // Autoplay restrictions still allow an explicit press of the play button.
      if (error.name === 'NotAllowedError') userPaused = true;
      else failed = true;
      updateControl();
    });
    updateControl();
  };
  heroMotionToggle.addEventListener('click', () => {
    userPaused = !heroVideo.paused;
    updateHeroMotion();
  });
  heroVideo.addEventListener('playing', () => {
    if (reduced.matches || capture || failed || userPaused || document.hidden) {
      updateHeroMotion();
      return;
    }
    heroMedia.classList.add('is-playing');
    updateControl();
  });
  heroVideo.addEventListener('pause', updateControl);
  heroVideo.addEventListener('error', () => { failed = true; updateHeroMotion(); });
  reduced.addEventListener('change', updateHeroMotion);
  document.addEventListener('visibilitychange', updateHeroMotion);
  updateHeroMotion();
}
const header = document.querySelector('.site-header');
let previousY = scrollY;
let scheduled = false;

if (header) {
  const root = document.documentElement;
  const utility = header.querySelector('.header-utility');
  let scrollDirection = 0;
  let directionDistance = 0;
  let scrollbarFrame = 0;
  let headerMoving = false;
  let lastHeaderBottom = -1;
  let lastUtilityBottom = -1;
  const updateScrollbar = () => {
    scrollbarFrame = 0;
    const bottom = Math.max(0, Math.ceil(header.getBoundingClientRect().bottom));
    const utilityBottom = Math.min(bottom, Math.max(0, Math.ceil(utility?.getBoundingClientRect().bottom || 0)));
    if (bottom !== lastHeaderBottom) {
      root.style.setProperty('--scrollbar-header-bottom', `${bottom}px`);
      lastHeaderBottom = bottom;
    }
    if (utilityBottom !== lastUtilityBottom) {
      root.style.setProperty('--scrollbar-utility-bottom', `${utilityBottom}px`);
      lastUtilityBottom = utilityBottom;
    }
    if (headerMoving) scheduleScrollbar();
  };
  const scheduleScrollbar = () => {
    if (!scrollbarFrame) scrollbarFrame = requestAnimationFrame(updateScrollbar);
  };
  // Follow the header only while it moves, including keyboard focus and menu opening.
  header.addEventListener('transitionrun', event => {
    if (event.target !== header || event.propertyName !== 'top') return;
    headerMoving = true;
    scheduleScrollbar();
  });
  for (const type of ['transitionend', 'transitioncancel']) {
    header.addEventListener(type, event => {
      if (event.target !== header || event.propertyName !== 'top') return;
      headerMoving = false;
      scheduleScrollbar();
    });
  }
  header.addEventListener('focusin', scheduleScrollbar);
  header.addEventListener('focusout', scheduleScrollbar);
  addEventListener('resize', scheduleScrollbar);
  addEventListener('pageshow', scheduleScrollbar);
  if ('ResizeObserver' in window) new ResizeObserver(scheduleScrollbar).observe(header);
  updateScrollbar();

  addEventListener('scroll', () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      const y = Math.max(0, Math.min(scrollY, root.scrollHeight - innerHeight));
      const delta = y - previousY;
      previousY = y;
      if (y === 0) {
        scrollDirection = 0;
        directionDistance = 0;
        header.classList.remove('header-visible');
      } else if (delta) {
        const direction = Math.sign(delta);
        if (direction !== scrollDirection) directionDistance = 0;
        scrollDirection = direction;
        directionDistance += Math.abs(delta);
        // Wait for a deliberate change of direction instead of trackpad jitter.
        if (y > 180 && directionDistance >= (direction < 0 ? 40 : 64)) {
          header.classList.toggle('header-visible', direction < 0);
        }
      }
      scheduled = false;
      scheduleScrollbar();
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
  }, { threshold: 0, rootMargin: '0px 0px -16px 0px' });
  // Reveal each content group together, without a cascade of individual rows.
  const groupSelector = '.section > .wrap,.closing-inner,.article-body > section,.directory-help';
  const targets = [...document.querySelectorAll(groupSelector)].filter(target => !target.parentElement?.closest(groupSelector));
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

// Decorative lighting and brand marks stay still during scrolling.

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
