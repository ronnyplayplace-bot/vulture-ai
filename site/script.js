document.addEventListener('DOMContentLoaded', () => {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ── Reveal-on-scroll ─────────────────────────────────── */
  if (reduceMotion) {
    document.querySelectorAll('.reveal').forEach((el) => el.classList.add('is-visible'));
  } else {
    const revealObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            revealObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -80px 0px' }
    );

    document.querySelectorAll('section, footer').forEach((block) => {
      block.querySelectorAll('.reveal').forEach((el, i) => {
        el.style.transitionDelay = `${Math.min(i, 5) * 0.09}s`;
        revealObserver.observe(el);
      });
    });
  }

  /* ── Hero parallax ────────────────────────────────────── */
  if (!reduceMotion) {
    const heroNoise = document.querySelector('.hero__noise');
    const heroGlow = document.querySelector('.hero__glow');
    const heroScroll = document.querySelector('.hero__scroll');

    window.addEventListener('scroll', () => {
      const y = window.scrollY;
      if (heroNoise) heroNoise.style.transform = `translateY(${y * 0.25}px)`;
      if (heroGlow) heroGlow.style.transform = `translateY(${y * 0.15}px)`;
      if (heroScroll) heroScroll.style.opacity = Math.max(0, 1 - y / 220);
    }, { passive: true });
  }

  /* ── Copy-to-clipboard on code blocks ─────────────────── */
  document.querySelectorAll('.code__copy').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const code = btn.parentElement.querySelector('code');
      if (!code) return;
      // strip the leading "$ " prompts, copy just the commands
      const text = code.textContent.replace(/^\s*\$\s?/gm, '').trim();
      try {
        await navigator.clipboard.writeText(text);
      } catch (e) {
        const r = document.createRange();
        r.selectNode(code);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(r);
        try { document.execCommand('copy'); } catch (_) {}
        sel.removeAllRanges();
      }
      const original = btn.textContent;
      btn.textContent = 'Copied';
      btn.classList.add('is-copied');
      setTimeout(() => {
        btn.textContent = original;
        btn.classList.remove('is-copied');
      }, 1600);
    });
  });
});
