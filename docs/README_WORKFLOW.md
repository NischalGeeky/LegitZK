# LegitZK demonstration walkthrough

Start the [local Studio](../README_PDF_STUDIO.md) at port 8001. Use the bundled synthetic vendor PDF throughout this demo.

## Redact and verify

1. In **Redact**, upload `fixtures/demo-vendor.pdf` and click **Upload and commit**.
2. Search for `Settlement Amount =>`, run **Detect fields**, and hide the settlement amounts on both pages. The first page reads `USD 5,230`. Select only the sensitive values you want covered. Use the preview tools to check page and pixel bounds.
3. Enter a recipient label and click **Review redaction plan**. Under **Register fields for private proofs**, choose the page 1 settlement region. Use **Settlement amount (page 1)** as the public label, **Amount (two decimal places)** as the datatype, **USD** as the currency code, and **5230** as the private value. Click **Add field**.
4. Click **Generate proof and PDF**. In **Verify**, upload both downloads and click **Verify disclosure**. For the following steps, keep the original Redact workspace open.

## Prove a private claim

1. In **Zero Knowledge Proof**, click **Use current Redact export**.
2. Choose the registered field, **At least**, and enter the public comparison amount **5000**. Click **Review condition**, confirm the displayed condition and click **Prove and verify**.
3. Repeat with **6000**. The owner can prove the first condition. LegitZK displays that no proof was generated for the second. The positive result is about the registered commitment.
4. With the [optional NLP model](../README_PDF_STUDIO.md#optional-local-tools) set up, try **Your question → Interpret question**, check the populated controls, and then use the same review and proof buttons.

For another owner, load the matching PDF and ZIP. Review the condition and use **Exchange a proof with someone else** to download the request. The owner loads it under **Respond as document owner**, approves the displayed condition, and returns the proof. The recipient verifies the returned proof with the original request and the matching disclosure loaded.

## Show a changed export

Use **Integrity lab → Edit a PDF test copy**. Upload the redacted export, select **Replace visible pixels**, preview the page, and draw around a visible value. Apply a short replacement and download the edited copy. Back in **Verify**, substitute it for the redacted PDF and keep the original ZIP. Compare the byte checks and the visual findings. For native source comparison, use the [source investigation guide](README_SOURCE_FORENSICS.md).

## Presentation summary

LegitZK commits to a raster of the original at ingestion and checks that the release follows the approved mask. The numeric proof uses a separate commitment to an owner-attested value. It can demonstrate a condition on that commitment while withholding the exact value. The reviewer is responsible for approving the mask and checking the value against the source.
