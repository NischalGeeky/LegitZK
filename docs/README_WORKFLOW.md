# LegitZK PDF Disclosure Studio | Working and presentation demo

## Open the studio on Windows

Run this from the installed release folder, with your existing `libsodium.dll` next to `rangeproof.py`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn pdf_studio:app --host 127.0.0.1 --port 8001 --no-access-log
```

Open [http://127.0.0.1:8001](http://127.0.0.1:8001). The [setup guide](../README_PDF_STUDIO.md) covers initial installation.

## Live demo with one page

1. Upload `fixtures/sample-1-page.pdf` and select **Upload and commit**.
2. In **Custom search phrases**, enter `Confidential reference =>`, then select **Detect fields**. The custom suggestion highlights the value after the label. Click **Hide** on that suggestion and dismiss duplicate or irrelevant candidates.
3. Under **Drag tool**, select **Mark to keep visible**. Drag around the public account status, or use **Enter region coordinates** to add the pixel box left 96, top 304, right 281, bottom 325 on page 1.
4. Enter `Demo reviewer` and select **Review redaction plan**. Check the shaded mask, tile count and any pixels added by grid alignment.
5. Select **Generate proof and PDF**. Download `redacted.pdf` and `legitzk-proof.zip`.
6. Open **Verify**. Upload the PDF and the ZIP, then choose **Verify disclosure**. Inspect the signed file inventory in the result.

For a document-style example, upload `fixtures/demo-lease.pdf` and search for `Settlement Amount =>`. Use the [corpus guide](README_PUBLIC_PDF_TESTING.md) to choose an additional public sample.

## Locate an altered disclosure

1. With the verified files still selected in **Verify**, open **Integrity lab**.
2. Run the metadata-only test. It reports changed PDF bytes with no visible differences at the comparison resolution.
3. Run the visible-edit test. It reports changed pixels and shows an annotated preview of the first changed page.
4. Download either test copy and substitute it into the PDF input in **Verify**. Keep the original ZIP selected. The report identifies the changed PDF and confirms which JSON files still match the signed inventory.

For a policy conflict, add a hide rectangle that shares an 8-pixel tile with a keep-visible selection. Review the reported conflict, adjust the boxes, and rebuild the plan.

## Suggested viva explanation

> The recipient checks the issuer Studio's signature on the exported file inventory. The proof then establishes consistency with commitments to the original raster while keeping the hidden pixels and private openings secret. The visual comparison uses the proof-authenticated redacted raster to identify page differences after a PDF byte mismatch. A human still approves the regions suggested by the detector.

See the [integrity benchmark](README_INTEGRITY_RESEARCH.md) for baseline comparisons and metrics.
