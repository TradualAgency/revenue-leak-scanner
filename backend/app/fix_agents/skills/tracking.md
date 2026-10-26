## Vakgebied: tracking en attributie

Doel: complete, consent-conforme conversiedata, zodat Meta/Google weer op echte verkopen optimaliseren.

Kijk vooral naar:
- **Consent Mode v2**: een CMP die `ad_storage`, `analytics_storage`, `ad_user_data` en `ad_personalization` zet vóór de tags laden. Op Shopify werkt dat via de Customer Privacy API (`window.Shopify.customerPrivacy`) of een gecertificeerde CMP-app. Beschrijf de default-consent-snippet en hoe de update-call werkt.
- **Meta CAPI**: de Facebook & Instagram-app (Shopify-kanaal) met datadeling op "Maximaal". Dedupliceer via `event_id` als er ook een handmatige pixel staat, en verwijder dubbele pixels uit `theme.liquid`.
- **GA4 / Google Ads**: de Google & YouTube-app of de Customer Events (web pixels) in Instellingen > Klantevenementen. Gebruik geen `checkout.liquid`-scripts meer (die zijn uitgefaseerd). Enhanced conversions staat aan.
- **Server-side tagging (sGTM)**: stel dit alleen voor als de omvang van het advertentiebudget het rechtvaardigt (zie `business_context`). Benoem dan de hosting-opties.
- **Dubbele events**: dezelfde pixel via de app én hardcoded geeft opgeblazen conversies.

De checklist noemt concreet: Meta Events Manager (Test Events, EMQ-score, deduplicatie), Google Tag Assistant / GA4 DebugView, en een testbestelling met een kortingscode van 100%.
