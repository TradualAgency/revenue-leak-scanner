## Vakgebied: checkout, structured data en feeds

Doel: minder afhakers in de checkout, rich results in Google en een Merchant Center-feed die door de controle komt.

**Checkout** (`checkout_flow`). Als `probe_status` `unreachable` is of `checkout_flow` null, doe geen uitspraken over de checkout-inhoud. Geef dan alleen een checklist om de checkout handmatig door te lopen.
- Gastcheckout via Instellingen > Checkout > Klantaccounts.
- Express-knoppen: Shop Pay, Apple Pay, Google Pay en iDEAL bovenaan. Op NL-stores staat iDEAL vóór creditcard.
- Minder adresvelden: zet bedrijfsnaam en adresregel 2 op optioneel of verborgen, en zet adres-autocomplete aan.
- Checkout-extensibility werkt alleen met apps en blocks, niet met `checkout.liquid`.

**Structured data** (`rich_results`, `seo_health`):
- Product-JSON-LD met `offers` (prijs, valuta, beschikbaarheid, `priceValidUntil`), `brand`, `sku`/`gtin`, en `aggregateRating`/`review` uit de review-app-metafields.
- Gebruik de Liquid-filter `structured_data` waar dat kan, en vul aan waar velden ontbreken.
- `Organization` en `BreadcrumbList`.
- Haal dubbele of conflicterende JSON-LD van apps en theme weg.

**Feeds** (`product_feeds`): het Google & YouTube-kanaal, GTIN/MPN, `google_product_category`, verzend- en retourinstellingen in Merchant Center, en de afkeurredenen.

De checklist bevat: de Rich Results Test van Google per paginatype, Merchant Center-diagnose, en een testbestelling op mobiel met tijdmeting.
