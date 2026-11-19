"""Local cumulative raster exposure for recorded exports of the same source."""
import hashlib
import hmac
import os
import sqlite3

import numpy as np
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from protocol import canonical


class ExposureHistory:
    def __init__(self, path, key):
        self.path = path
        self.index_key = hmac.digest(key, b"exposure-index/v1", "sha256")
        self.cipher = AESGCM(hmac.digest(key, b"exposure-masks/v1", "sha256"))
        with sqlite3.connect(self.path) as con:
            con.execute("""CREATE TABLE IF NOT EXISTS exposure_v1 (
                scope BLOB PRIMARY KEY, ciphertext BLOB NOT NULL, exports INTEGER NOT NULL
            )""")

    def evaluate(self, manifest, request, masked, record=False, groups=()):
        dimensions = manifest["pages"]
        scope = hmac.digest(self.index_key, canonical([
            manifest["source_sha256"], manifest["profile"], dimensions, request["audience"]
        ]), "sha256")
        lengths = [w * h for w, h in dimensions]
        current = np.zeros(sum(lengths), dtype=bool)
        offsets = [0, *np.cumsum(lengths).tolist()]
        for page, x, y, right, bottom in masked:
            w, h = dimensions[page]
            pixels = current[offsets[page]:offsets[page + 1]].reshape(h, w)
            pixels[y:bottom, x:right] = True

        with sqlite3.connect(self.path, isolation_level="IMMEDIATE") as con:
            if record:
                con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT ciphertext, exports FROM exposure_v1 WHERE scope=?", (scope,)).fetchone()
            if row:
                ciphertext, count = row
                aad = scope + count.to_bytes(8, "big")
                packed = self.cipher.decrypt(ciphertext[:12], ciphertext[12:], aad)
                previous = np.unpackbits(np.frombuffer(packed, dtype=np.uint8), count=len(current)).astype(bool)
            else:
                count = 0
                previous = np.ones_like(current)
            remaining = previous & current
            if record:
                nonce = os.urandom(12)
                aad = scope + (count + 1).to_bytes(8, "big")
                ciphertext = nonce + self.cipher.encrypt(nonce, np.packbits(remaining).tobytes(), aad)
                con.execute("INSERT OR REPLACE INTO exposure_v1 VALUES (?, ?, ?)", (scope, ciphertext, count + 1))

        pages = []
        for index, length in enumerate(lengths):
            start, end = offsets[index:index + 2]
            hidden = int(current[start:end].sum())
            combined_hidden = int(remaining[start:end].sum())
            pages.append({
                "page": index + 1, "total_pixels": length, "hidden_this_release": hidden,
                "hidden_across_releases": combined_hidden, "previously_visible_but_now_hidden": hidden - combined_hidden,
            })
        def hidden_on(mask, box):
            page, x, y, right, bottom = box
            w, h = dimensions[page]
            pixels = mask[offsets[page]:offsets[page + 1]].reshape(h, w)
            return pixels[y:bottom, x:right].any()

        reconstructed = []
        if count:
            for _, category, occurrences in groups:
                # The whole occurrence is unmasked in the union of recorded and proposed pixels.
                for occurrence in occurrences:
                    if (any(hidden_on(previous, box) for box in occurrence)
                            and any(hidden_on(current, box) for box in occurrence)
                            and not any(hidden_on(remaining, box) for box in occurrence)):
                        reconstructed.append({"category": category, "page": occurrence[0][0] + 1})
        return {"recorded_exports": count, "pages": pages, "reconstructed_fields": reconstructed}
