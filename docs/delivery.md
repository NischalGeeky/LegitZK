# Final archive verification report

This report covers the supplied final project archive, with the PDF Disclosure Studio as the primary application. The documentation update preserves the supplied application code, fixtures, model files, and archived measurements.

| Check | Observed result |
|---|---|
| Python test suite | All 50 tests passed with `python -m unittest discover -s tests -q`. |
| Synthetic vendor walkthrough | Exercised via the Studio API. It detected both settlement regions, generated and verified a disclosure, proved the page 1 amount was at least USD 5,000, and returned no proof for the USD 6,000 threshold. |
| JavaScript syntax | Both `pdf_web/studio.js` and `web/app.js` passed `node --check`. |
| Browser and Windows execution | This documentation audit verified the walkthrough at the API level. No interactive browser or native Windows run was performed for this revision. The repository browser script targets the earlier contract app. |
| Benchmarks and model | The committed JSON files preserve historical synthetic measurements. This audit did not rerun timing experiments or model evaluation. |

The Studio uses a local trusted ingestion key, approved masks, and temporary owner workspaces. Field proofs use owner-attested values. The fixed-schema contract workflow and numeric credential CLI have separate [operations](operations.md) and [proof](README_NUMERIC_CLAIMS.md) documentation. Start with the [Studio guide](../README_PDF_STUDIO.md) for the main application.
