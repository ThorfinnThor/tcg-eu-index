# Magic card-image publication review

Review date: 2026-08-30

Decision: `operator_approved_for_publication`

The operator confirmed on 2026-08-30 that the required publication clearance is held for the implementation-plan scope. The image pipeline may therefore expose exact Scryfall matches with the required attribution and unofficial-content notices. This repository records the operator decision; it is not independent legal advice.

## Official evidence reviewed

- [Wizards Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy)
- [Wizards Terms](https://company.wizards.com/en/legal/terms)
- [Scryfall image documentation](https://scryfall.com/docs/api/images)
- [Scryfall API traffic guidance](https://scryfall.com/docs/faqs/i-m-having-trouble-accessing-the-scryfall-api-or-i-m-blocked-17)

The Fan Content Policy permits free-access fan websites to use Wizards art and permits sponsorship, advertising, donations, and some click revenue. It also requires an unofficial-fan-content notice and preservation of existing legal notices. The current Wizards Terms describe the Fan Content Policy as permitting only noncommercial activities and prohibit exploitation outside an express license. Neither source clearly addresses a free index website whose card pages contain marketplace affiliate links.

Scryfall provides image locations and technical usage guidance, but it is not treated here as granting the underlying Wizards or artist copyright for this commercial context.

## Recorded resolution

The operator confirmed that the implementation-plan use is approved, including the free-access index presentation and planned affiliate-funded marketplace links. The publication policy records that confirmation and the reviewed source material.

Any later expansion beyond that scope, provider change, or takedown request requires a new review before the policy is widened.

## Technical consequences

- Exact Scryfall matches are published as `exact` in public JSON.
- No `cards.scryfall.io` URL is included in an unresolved public record.
- `CARD_IMAGES_ENABLED` and `CARD_IMAGES_MAGIC` cannot bypass the policy gate.
- The activation report separately tracks matching quality and review gates.
- The UI displays the required unofficial-content and Scryfall attribution notices wherever images are shown.
