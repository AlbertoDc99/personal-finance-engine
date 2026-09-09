# Engineering a financial domain

## Problem and scope

A financial dashboard can look plausible while conflating deposits with returns, stale prices with fresh observations or missing data with zero. The calculation layer needs to make those distinctions before an interface formats a number.

The public extraction retains the domain's existing Spanish names to preserve its relationship to the original implementation. Its modules can be read independently of the production application. References to private specification sections in source docstrings are historical traceability labels; the public contract is described here and exercised by the included tests.

## Decisions visible in code

1. `Money` carries currency alongside a `Decimal`; incompatible currencies cannot silently be combined.
2. An operation has an identity, effective date, status and legs. Projection handles the active history rather than assuming every row is an independent cash movement.
3. Price and FX observations retain source and effective dates. A carried observation stays marked as carried.
4. A valuation can be incomplete. Known value is distinct from a demonstrable total.
5. Performance separates external contributions from investment result. Daily TWR uses the documented beginning-of-day flow convention; XIRR uses dated cash flows and ACT/365.

The valuation index is optimized for historical lookup by effective date. It is not a complete point-in-time market-vintage engine: replay at an earlier knowledge timestamp would need filtering on receipt time as well.

The public edition adds two reviewed boundary guards to the extracted domain: TWR requires one currency across the full series, and same-day-only XIRR inputs return an unknown result instead of an arbitrary rate. Regression tests accompany both changes.

## Tradeoffs

- Pure Python and the standard library make the domain easy to test and run offline.
- A focused extraction is easier to inspect than the entire private system, but it does not demonstrate operational concurrency or persisted transactions.
- Explicit incomplete states require more care from consumers; they prevent a misleading zero or total from reaching the dashboard.
- Synthetic fixtures make edge cases reproducible. They do not prove compatibility with all possible provider files or financial products.

## Questions this project can support in an interview

- Why does a EUR 200 deposit not increase investment profit by EUR 200?
- What should a dashboard display when one instrument lacks a price?
- How would you add a provider without coupling domain formulas to HTTP?
- How would you extend this design with persisted revisions and transactional publication?

The final question is an extension discussion, not a claim that persistence is implemented in this extraction.
