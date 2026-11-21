# LegitZK evaluation | Public PDFs and measured results

## Public PDF test plan

| Corpus | Use |
|---|---|
| IRS blank W-9 and W-4 | Use public PDF forms to test boxes, adjacent fields, and multi-page policy checks. Make labeled copies with fictitious visible values for ground truth. [W-9](https://www.irs.gov/pub/irs-pdf/fw9.pdf) · [W-4](https://www.irs.gov/pub/irs-pdf/fw4.pdf) |
| GovInfo Federal Register | Use individually published short notices for multi-column page layouts. [Example PDF](https://www.govinfo.gov/content/pkg/FR-2025-12-08/pdf/2025-22177.pdf) · [Collection](https://www.govinfo.gov/app/collection/FR) |
| veraPDF corpus | Select supported PDF/A samples with attachments, annotation layers or unusual PDF structure. Check the output for inherited content. [Corpus](https://github.com/veraPDF/veraPDF-corpus) |
| Scan control | Use image-only derivatives of eligible forms to compare local OCR and manual review. Record resolution and language settings. |

Record each source URL, date, hash and annotation policy. Suggested set: four short notices, two forms with fictional text values, three scan derivatives and three structural cases. Independently annotate boxes that should remain visible and boxes that must be hidden. Use identical approved regions for every planner comparison and count rejected inputs. Protect text and evaluate coverage visually on rendered output if a form widget or annotation isn't visible in the source preview. This public corpus is a protocol for follow-up evaluation. The results below use synthetic fixtures only.

## Reproduce the included experiments

From the installed project folder:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m benchmarks.adaptive_studio
```

The benchmark uses three synthetic lease, vendor and statement layouts with one, two and three pages respectively. It builds one adaptive-profile commitment per source, obtains approved ground-truth rectangles from the fixtures and compares all modes under the same limits. Each proof run verifies its output. Table values are medians of three runs after a warm-up on Linux. Proof timing includes PDF output, package construction or verifier reconstruction. [Raw measurements](../benchmarks/adaptive-results.json)

| Synthetic layout | Mode | Extra pixels hidden | Proof tiles | Verify time | JSON evidence |
|---|---:|---:|---:|---:|---:|
| Lease | Fixed 32 | 17,171 | 330 | 73.8 ms | 152 KB |
| Lease | Adaptive | 4,627 | 525 | 99.8 ms | 168 KB |
| Lease | Fixed 8 | 4,627 | 5,100 | 796.8 ms | 476 KB |
| Vendor | Fixed 32 | 30,866 | 660 | 150.0 ms | 302 KB |
| Vendor | Adaptive | 8,338 | 1,038 | 197.9 ms | 334 KB |
| Vendor | Fixed 8 | 8,338 | 10,200 | 1,655.8 ms | 950 KB |
| Statement | Fixed 32 | 56,001 | 990 | 219.8 ms | 442 KB |
| Statement | Adaptive | 15,297 | 1,719 | 316.7 ms | 499 KB |
| Statement | Fixed 8 | 15,297 | 15,300 | 2,372.8 ms | 1,411 KB |

Adaptive kept the same fine-grid mask while verifying faster and sending less evidence than fixed-8 on these fixtures. Fixed-32 remained faster but hid more pixels. The proof itself was 160 bytes in every mode. The comparison shares a multi-resolution commitment inventory and does not measure the ingestion advantage of an implementation that commits only to one fixed size.

| Detection | Synthetic targets covered | False sensitive suggestions |
|---|---:|---:|
| Rules only | 12/21 | 0 |
| Rules plus local classifier | 18/21 | 0 |

The target test counts all seeded standard sensitive fields, including omissions by candidate extraction. A suggestion had to overlap more than 70% of a target box to count as a hit. The held-out synthetic wording still shares vocabulary with the tiny training corpus. Repeated pages repeat the same label layouts. These are coverage counts on this fixture, with no claim of generalization rates on real legal documents. Custom search found three additional settlement fields outside the standard-category test. Local OCR also found a labeled account number in a separate image-only smoke test.

## Included model evaluation

The archived [adapter evaluation](../claim-model/evaluation.json) records 41 exact structured-condition matches from 78 answerable cases and 0 correct clarification responses from 18 cases. These are held-out synthetic templates and labels, with no claim about real-document accuracy. The result supports retaining human review and the manual comparison controls.

With the [optional NLP dependencies](../README_PDF_STUDIO.md#optional-local-tools) installed, run `python train_claim_model.py --evaluate-only`. Reproduction of the two training stages uses `python train_claim_model.py --output claim-model-initial --skip-evaluation` followed by `python train_claim_model.py --resume claim-model-initial --steps 95`. Training can write a new adapter to the default output directory. Use `--output` to preserve the supplied adapter.

## Checks for this archive

The [delivery report](delivery.md) lists the current validation. The public PDF corpus above is a test plan. The included performance and detection measurements are historical synthetic runs.
