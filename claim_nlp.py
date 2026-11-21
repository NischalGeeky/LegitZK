"""Translate a question and public field catalog into a draft proof condition."""
import json
import os
import re
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from threading import Lock
from unicodedata import normalize

from field_claim import OPERATORS
from field_equality import NUMERIC, typed
from protocol import shape

BASE = "google/flan-t5-small"
BASE_REVISION = "0fc9ddf78a1e988dac52e2dac162b0ede4fd74ab"
DEFAULT_MODEL = Path(__file__).resolve().parent / "claim-model"
MODEL_LOCK = Lock()


def prompt(question, fields):
    catalog = [
        [index + 1, field["label"] + (f' ({field["description"]})' if field.get("description") else ""),
         field["type"], field["unit"]]
        for index, field in enumerate(fields)
    ]
    return (
        'Translate to JSON {"field":number,"operator":string,"values":[string]}. '
        'Operators: eq, ge, gt, le, lt, between (inclusive). '
        'Use the original threshold units, and decimal digits. '
        'For ambiguous, unsupported, or missing fields output {"status":"clarify"}. '
        f"Fields: {json.dumps(catalog, ensure_ascii=False)} Question: {question}"
    )


def model_path():
    return Path(os.environ.get("LEGITZK_CLAIM_MODEL", str(DEFAULT_MODEL)))


@lru_cache(maxsize=1)
def load_model(path):
    if not any(Path(path, name).is_file() for name in ("config.json", "adapter_config.json")):
        raise ValueError("The local question model is unavailable. Use the manual condition below.")
    try:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    except ImportError:
        raise ValueError("Install the optional NLP dependencies to use the local question model.") from None
    try:
        tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
        if Path(path, "adapter_config.json").is_file():
            from peft import PeftModel
            base = AutoModelForSeq2SeqLM.from_pretrained(
                BASE, revision=BASE_REVISION, local_files_only=True, use_safetensors=True)
            model = PeftModel.from_pretrained(base, path, local_files_only=True)
        else:
            model = AutoModelForSeq2SeqLM.from_pretrained(path, local_files_only=True, use_safetensors=True)
    except (ImportError, OSError) as error:
        raise ValueError("Question model setup is incomplete. Follow the README or enter a condition manually.") from error
    torch.set_num_threads(min(4, torch.get_num_threads()))
    model.eval()
    return tokenizer, model


def read_prediction(raw):
    # The FLAN-T5 tokenizer cannot represent braces in generated text.
    raw = raw.strip()
    if raw.startswith('"'):
        raw = "{" + raw + "}"
    return json.loads(raw)


def decode(raw, fields):
    try:
        value = read_prediction(raw)
        if value == {"status": "clarify"}:
            raise ValueError
        shape(value, ("field", "operator", "values"))
        index = value["field"]
        if type(index) is not int or not 1 <= index <= len(fields) or value["operator"] not in OPERATORS:
            raise ValueError
        return fields[index - 1]["id"], value["operator"], value["values"]
    except (ValueError, TypeError):
        raise ValueError("No supported condition was identified. Rephrase or enter the condition manually.") from None


def check_currency(question, field):
    if field["type"] != "amount":
        return
    symbols = {"₹": {"INR"}, "€": {"EUR"}, "£": {"GBP"}, "$": {"USD", "CAD", "AUD", "NZD", "SGD", "HKD"}}
    unit = field["unit"]
    codes = set(re.findall(r"\b(?:USD|INR|EUR|GBP|CAD|AUD|NZD|SGD|HKD|JPY|CHF)\b", question.upper()))
    if codes - {unit} or any(symbol in question and unit not in units for symbol, units in symbols.items()):
        raise ValueError(f"The question names a different currency. This field uses {unit}.")

def check_thresholds(question, field, values):
    """Reject invented numeric operands while leaving interpretation to the model."""
    kind, unit = field["type"], field["unit"]
    if kind not in NUMERIC:
        source = normalize("NFKC", question).casefold()
        if any(typed(value, kind, unit).casefold() not in source for value in values):
            raise ValueError("State the exact comparison date or code, or enter the condition manually.")
        return
    question = normalize("NFKC", question).lower().replace("−", "-")
    # Spelled-out numbers are interpreted by the model and confirmed in the form.
    number_word = r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|lakh|crore)\b"
    if re.search(number_word, question):
        return
    mentions = set()
    pattern = r"(?<![\w.])([+-]?\d+(?:,\d+)*(?:\.\d+)?)(?:\s*(grand|[km]))?(?!\w)"
    for match in re.finditer(pattern, question):
        raw, suffix = match.groups()
        factor = {"k": 1000, "grand": 1000, "m": 1_000_000}.get(suffix, 1)
        mentions.add(Decimal(raw.replace(",", "")) * factor)
    scale = 100 if kind == "amount" else 1
    thresholds = {Decimal(typed(value, kind, unit)) / scale for value in values}
    if not thresholds <= mentions:
        raise ValueError("The question does not clearly supply these thresholds. State the value or enter the condition manually.")


def interpret(question, fields):
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 300:
        raise ValueError("Enter a question of up to 300 characters.")
    with MODEL_LOCK:
        tokenizer, model = load_model(str(model_path().resolve()))
        import torch

        tokens = tokenizer(prompt(question, fields), return_tensors="pt")
        if tokens.input_ids.shape[1] > 1024:
            raise ValueError("Shorten the question or choose a field manually.")
        with torch.inference_mode():
            predicted = model.generate(**tokens, max_new_tokens=96, num_beams=3)
        return decode(tokenizer.decode(predicted[0], skip_special_tokens=True), fields)
