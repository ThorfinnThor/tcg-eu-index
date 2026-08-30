# Magic card-image publication review

Review date: 2026-08-30

Decision: `pending_written_clarification`

The image pipeline may use Scryfall metadata and private provider snapshots, but it must not expose Magic artwork URLs until the commercial publication question is explicitly resolved.

## Official evidence reviewed

- [Wizards Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy)
- [Wizards Terms](https://company.wizards.com/en/legal/terms)
- [Scryfall image documentation](https://scryfall.com/docs/api/images)
- [Scryfall API traffic guidance](https://scryfall.com/docs/faqs/i-m-having-trouble-accessing-the-scryfall-api-or-i-m-blocked-17)

The Fan Content Policy permits free-access fan websites to use Wizards art and permits sponsorship, advertising, donations, and some click revenue. It also requires an unofficial-fan-content notice and preservation of existing legal notices. The current Wizards Terms describe the Fan Content Policy as permitting only noncommercial activities and prohibit exploitation outside an express license. Neither source clearly addresses a free index website whose card pages contain marketplace affiliate links.

Scryfall provides image locations and technical usage guidance, but it is not treated here as granting the underlying Wizards or artist copyright for this commercial context.

## Required resolution

Before changing `artwork_publication` to `approved`, retain one of:

1. written permission or clarification from Wizards covering the intended free-access, affiliate-funded card-index use; or
2. a written legal review concluding that the planned use is covered, with the reviewer, jurisdiction, scope, and takedown process recorded.

Approval must also specify whether direct Scryfall hotlinking is acceptable or whether a separately licensed image source is required.

## Technical consequences

- Exact Scryfall matches remain `blocked_legal` in public JSON.
- No `cards.scryfall.io` URL is included in an unresolved public record.
- `CARD_IMAGES_ENABLED` and `CARD_IMAGES_MAGIC` cannot bypass the policy gate.
- The activation report must show all release gates passing before publication.
- If approved, the UI must display the required unofficial-content and Scryfall attribution notices wherever images are shown.
