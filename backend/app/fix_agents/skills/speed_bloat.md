## Vakgebied: laadsnelheid en app-bloat

Doel: mobiele LCP onder 2,5 s, INP onder 200 ms, CLS onder 0,1, zonder functionaliteit te breken die omzet oplevert.

Kijk vooral naar:
- **Scripts in `<head>`** zonder `defer`/`async`, en app-embeds die op elke pagina laden terwijl ze maar op één paginatype nodig zijn. Conditioneel laden met `{% if template.name == 'product' %}` is vaak de grootste winst.
- **Overbodige of dubbele apps** (`bloat_what_must_go`, `third_party_scripts`, `cost_analysis`): twee review-apps, oude tracking-scripts, restanten van verwijderde apps in `theme.liquid` of `snippets/`. Zet ze in `apps_to_remove`, met de reden en de vervanger als die er is.
- **LCP-element**: de hero- of productafbeelding. Daarvoor `loading="eager"`, `fetchpriority="high"`, `image_url` met `width` + `srcset` via `image_tag`, en geen lazy-load op de eerste afbeelding. Zet een `preload` alleen voor de echte LCP-resource.
- **Fonts**: `font_display: swap`, preconnect naar `fonts.shopifycdn.com`, minder gewichten.
- **INP**: zware chat-, popup- en tracking-widgets pas laden na interactie of idle (`requestIdleCallback`, of een snippet dat laadt bij de eerste scroll of klik).
- **CLS**: vaste afmetingen of `aspect-ratio` voor afbeeldingen, banners en app-blocks.

Verifieer met `run_analyzer` → `performance` op de zwaarste pagina. Verwijs in de checklist naar PageSpeed Insights (labdata direct, velddata na 28 dagen).
