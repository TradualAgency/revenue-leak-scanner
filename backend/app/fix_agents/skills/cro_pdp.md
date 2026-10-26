## Vakgebied: CRO op productpagina, collectie en winkelmand

Doel: meer bezoekers die een product bekijken, toevoegen aan de winkelmand en doorgaan naar de checkout.

Kijk vooral naar:
- **Social proof**: een reviewwidget dicht bij de prijs en de ATC-knop, sterren op collectiekaarten, en het aantal reviews zichtbaar. Werk met app-blocks in `templates/product.json` als de review-app ze levert.
- **Boven de vouw op mobiel**: titel, prijs, varianten, ATC en een levertijd- en verzendbelofte zonder te scrollen. Een sticky ATC op mobiel.
- **Verzendduidelijkheid**: drempel voor gratis verzending, levertijd en retourbeleid bij de ATC. Een voortgangsbalk naar gratis verzending in de cart drawer, via `cart.total_price` in Liquid.
- **Cross-sell**: Shopify Search & Discovery-aanbevelingen (`recommendations.products`) op de PDP en in de winkelmand.
- **Productcontent en voorraad** (`shopify_catalog`, `get_products_sample`): producten zonder beschrijving of met weinig media, en uitverkochte producten die nog prominent staan.
- **E-mailcapture**: een signup die niet stoort (geen popup die meteen verschijnt op mobiel), met een duidelijk aanbod.

Lever wijzigingen als JSON-template-blocks (`templates/*.json`) of als section-Liquid, met de exacte copy in het Nederlands. Elke fix krijgt een A/B-test of voor-na-meting in de checklist (Shopify Analytics: ATC-rate, conversie per apparaat).
