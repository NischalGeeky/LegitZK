"""Download the public FLAN-T5 Small base weights for offline inference."""
import os

from claim_nlp import BASE, BASE_REVISION

if __name__ == "__main__":
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from huggingface_hub import snapshot_download

    snapshot_download(BASE, revision=BASE_REVISION,
                      allow_patterns=["config.json", "generation_config.json", "model.safetensors"])
    print("FLAN-T5 Small base weights are ready. Start the PDF studio.")
