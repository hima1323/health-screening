import { useEffect } from 'react';

/** Give each page its own browser-tab title ("Your results · Aura Screen") — screen readers announce it on arrival. */
export default function usePageTitle(title, app = 'Aura Screen') {
  useEffect(() => {
    if (title) document.title = `${title} · ${app}`;
  }, [title, app]);
}
