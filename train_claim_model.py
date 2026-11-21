"""Fine-tune and evaluate the local FLAN-T5 claim translator on synthetic questions."""
import argparse
import json
from pathlib import Path
from random import Random

from claim_nlp import BASE, BASE_REVISION, decode, prompt, read_prediction
TRAIN_FIELDS = (
    ("Age at visit", "integer", "", ("age at the appointment", "patient's age at the visit")),
    ("Resting pulse", "integer", "", ("resting heart rate", "pulse at rest")),
    ("Checking closing balance", "amount", "USD", ("checking balance at month-end", "checking closing balance")),
    ("Monthly net wages", "amount", "INR", ("monthly take-home pay", "net monthly salary")),
    ("Visit diagnosis code", "code", "", ("diagnostic code from the visit", "visit diagnosis code")),
    ("Date of discharge", "date", "", ("hospital discharge date", "date of discharge")),
)
EVAL_FIELDS = (
    ("Age at admission", "integer", "", ("age on admission", "patient's age at admission")),
    ("Heart rate at triage", "integer", "", ("triage heart rate", "pulse during triage")),
    ("Share draft ending balance", "amount", "USD", ("checking ending balance", "final checking balance")),
    ("Monthly gross pay", "amount", "INR", ("gross monthly wages", "monthly pay before deductions")),
    ("Primary diagnosis code", "code", "", ("primary diagnostic code", "main diagnosis code")),
    ("Date of first appointment", "date", "", ("date of the initial appointment", "first visit date")),
)
TRAIN_PATTERNS = {
    "eq": ("Did {f} equal {a}?", "Can you confirm {f} was exactly {a}?"),
    "ge": ("Was {f} at least {a}?", "Did {f} reach {a} or above?"),
    "gt": ("Was {f} above {a}?", "Did {f} exceed {a}?"),
    "le": ("Was {f} no more than {a}?", "Did {f} stay at or below {a}?"),
    "lt": ("Was {f} under {a}?", "Did {f} come in below {a}?"),
    "between": ("Was {f} between {a} and {b}, inclusive?", "Was {f} in the range {a} to {b}?"),
}
EVAL_PATTERNS = {
    "eq": ("Does {a} exactly match {f}?",),
    "ge": ("Was {f} {a} or higher?",),
    "gt": ("Did {f} go over {a}?",),
    "le": ("Was {a} an upper limit for {f}?",),
    "lt": ("Was {a} more than {f}?",),
    "between": ("Can you verify {f} was within {a}–{b} including the endpoints?",),
}


def examples(evaluation=False, augment=False):
    rng = Random(222 if evaluation else 101)
    fields = EVAL_FIELDS if evaluation else TRAIN_FIELDS
    patterns = EVAL_PATTERNS if evaluation else TRAIN_PATTERNS
    if augment and not evaluation:
        patterns = {
            **patterns,
            "ge": (*patterns["ge"], "Did {f} finish with {a} or more?",
                   "Did {f} get to {a} or higher?", "Was {f} already {a} by then?"),
            "le": (*patterns["le"], "Did {f} finish with {a} or less?",
                   "Was {f} {a} or lower?"),
        }
    rows = []
    for iteration in range(3 if evaluation else 12):
        for label, kind, unit, aliases in fields:
            others = [item[:3] for item in fields if item[0] != label]
            catalog = [(label, kind, unit), *rng.sample(others, rng.randint(0, 5) if augment else 3)]
            rng.shuffle(catalog)
            index = catalog.index((label, kind, unit)) + 1
            schema = [
                {"id": str(slot), "label": name, "type": datatype, "unit": units}
                for slot, (name, datatype, units) in enumerate(catalog, 1)
            ]
            number = rng.choice((18, 60, 75, 100)) if kind == "integer" else rng.randint(1, 15)
            if kind == "amount":
                symbol = "$" if unit == "USD" else "₹"
                raw_a, raw_b = f"{symbol}{number:,},000", f"{symbol}{number + 3:,},000"
                a, b = str(number * 1000), str((number + 3) * 1000)
                words = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen".split()
                if iteration % 3 == 0 and unit == "USD":
                    raw_a = f"{words[number - 1]} grand"
            elif kind == "integer":
                a = raw_a = str(number)
                b = raw_b = str(number + 10)
            elif kind == "date":
                a = raw_a = f"2025-04-{iteration + 10}"
            else:
                a = raw_a = rng.choice(("E11.9", "I10", "J45.909"))
            supported = patterns if kind in ("amount", "integer") else ("eq",)
            for operator in supported:
                for pattern in patterns[operator]:
                    question = pattern.format(f=rng.choice(aliases), a=raw_a,
                                              b=raw_b if operator == "between" else "")
                    values = [a, b] if operator == "between" else [a]
                    target = {"field": index, "operator": operator, "values": values}
                    rows.append((prompt(question, schema), target, schema))
            if augment and label == "Age at visit":
                question = f"Had the patient turned {raw_a} by the time of the visit?"
                rows.append((prompt(question, schema), {"field": index, "operator": "ge", "values": [a]}, schema))
            if augment and kind == "amount":
                if unit == "USD":
                    question = f"Did checking finish the month with {raw_a} or more?"
                else:
                    question = f"Was take-home pay {raw_a} or more this month?"
                rows.append((prompt(question, schema), {"field": index, "operator": "ge", "values": [a]}, schema))
            other_question = rng.choice((
                f"Tell me the exact value of {label}.", f"Was {label} unusually high?",
                "Was the document signed before the primary contact moved?",
            ) if not evaluation else (
                f"How big was {label}?", "Is the account number divisible by seven?",
            ))
            rows.append((prompt(other_question, schema), {"status": "clarify"}, schema))
    rng.shuffle(rows)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--output", default="claim-model")
    parser.add_argument("--steps", type=int, default=450)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--evaluate-only", action="store_true")
    parser.add_argument("--resume", help="Continue from a trained adapter with additional phrasing variants.")
    parser.add_argument("--skip-evaluation", action="store_true")
    args = parser.parse_args()
    import torch
    from peft import LoraConfig, PeftModel, TaskType, get_peft_model
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, set_seed

    set_seed(42)
    torch.set_num_threads(args.threads)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    output = Path(args.output)
    revision = {"revision": BASE_REVISION} if args.base == BASE else {}
    tokenizer = (AutoTokenizer.from_pretrained(output) if args.evaluate_only
                 else AutoTokenizer.from_pretrained(args.base, **revision))
    model = AutoModelForSeq2SeqLM.from_pretrained(args.base, use_safetensors=True, **revision)
    if args.evaluate_only:
        evaluate(PeftModel.from_pretrained(model, output).to(device), tokenizer, device, output)
        return
    config = LoraConfig(task_type=TaskType.SEQ_2_SEQ_LM, r=16, lora_alpha=32,
                        lora_dropout=0.05, target_modules=["q", "v"])
    model = (PeftModel.from_pretrained(model, args.resume, is_trainable=True)
             if args.resume else get_peft_model(model, config)).to(device)
    optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad),
                                  lr=0.0006 if args.resume else 0.001)
    train = examples(augment=bool(args.resume))
    rng = Random(42)
    model.train()
    for step in range(args.steps):
        batch = rng.sample(train, 8)
        source = tokenizer([row[0] for row in batch], padding=True, return_tensors="pt").to(device)
        labels = tokenizer([json.dumps(row[1], separators=(",", ":")) for row in batch],
                           padding=True, return_tensors="pt").input_ids.to(device)
        labels[labels == tokenizer.pad_token_id] = -100
        loss = model(**source, labels=labels).loss
        loss.backward()
        optimizer.step()
        optimizer.zero_grad()
        if (step + 1) % 50 == 0:
            print(f"Step {step + 1}: loss {loss.item():.3f}", flush=True)
    model.save_pretrained(output)
    tokenizer.save_pretrained(output)
    if not args.skip_evaluation:
        evaluate(model, tokenizer, device, output)


def evaluate(model, tokenizer, device, output):
    import torch

    model.eval()
    results = {"condition": [0, 0], "clarify": [0, 0]}
    rows = examples(evaluation=True)
    with torch.inference_mode():
        for start in range(0, len(rows), 8):
            batch = rows[start:start + 8]
            inputs = tokenizer([row[0] for row in batch], padding=True, return_tensors="pt").to(device)
            generated = model.generate(**inputs, max_new_tokens=96, num_beams=3)
            predictions = tokenizer.batch_decode(generated, skip_special_tokens=True)
            for raw, (_, target, schema) in zip(predictions, batch):
                category = "clarify" if "status" in target else "condition"
                try:
                    matched = (read_prediction(raw) == target if category == "clarify" else
                               decode(raw, schema) == (str(target["field"]), target["operator"], target["values"]))
                except ValueError:
                    matched = False
                results[category][0] += int(matched)
                results[category][1] += 1
    report = {key: {"correct": counts[0], "total": counts[1]} for key, counts in results.items()}
    print(json.dumps(report), flush=True)
    (output / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
