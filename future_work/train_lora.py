"""
train_lora.py
-------------
LoRA fine-tuning of Qwen2.5-Coder-0.5B-Instruct on the MCL repair dataset
(Section 9.4 of the Phase 1 report). Written for a free Google Colab GPU.

What it does
    * reads dataset/out/train.jsonl (and val.jsonl) built by build_dataset.py
    * formats every example with the chat template, and trains ONLY on the
      corrected-program tokens (the prompt is masked out)
    * wraps the base model with LoRA adapters (a small set of extra weights),
      so only ~1% of parameters are trained
    * saves the adapter + tokenizer + a training log to --out

Quick check that everything works (about a minute):
    python train_lora.py --smoke
Real run:
    python train_lora.py --out /content/mcl_adapter
"""

import sys
import argparse
import inspect
import json
import os
import random
import time

# reduces GPU memory fragmentation; must be set before torch is imported
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from mcl_prompt import tokenize_for_training

DEFAULT_BASE = "Qwen/Qwen2.5-Coder-0.5B-Instruct"
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def load_rows(path, limit=None, seed=0):
    with open(path) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if limit and len(rows) > limit:
        random.Random(seed).shuffle(rows)
        rows = rows[:limit]
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", default="dataset/out/train.jsonl")
    ap.add_argument("--val", default="dataset/out/val.jsonl")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--out", default="mcl_adapter")
    ap.add_argument("--epochs", type=float, default=2)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--max-len", type=int, default=1536)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--max-train-samples", type=int, default=1500,
                    help="use a random subset of the training set (0 = use all)")
    ap.add_argument("--max-val-samples", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--smoke", action="store_true", help="tiny 1-epoch run to check the setup works")
    args = ap.parse_args()

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import (AutoModelForCausalLM, AutoTokenizer, DataCollatorForSeq2Seq,
                              Trainer, TrainingArguments, set_seed)

    if args.smoke:
        args.max_train_samples, args.max_val_samples, args.epochs = 64, 16, 1
    set_seed(args.seed)

    has_gpu = torch.cuda.is_available()
    print(f"GPU available: {has_gpu}" + (f" ({torch.cuda.get_device_name(0)})" if has_gpu else ""))
    if not has_gpu:
        print("WARNING: no GPU found. In Colab choose Runtime > Change runtime type > T4 GPU. "
              "Training on CPU will be extremely slow.")

    # ---- data ---------------------------------------------------------------
    tokenizer = AutoTokenizer.from_pretrained(args.base)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    train_rows = load_rows(args.train, args.max_train_samples or None, args.seed)
    val_rows = load_rows(args.val, args.max_val_samples or None, args.seed)
    print(f"Training examples: {len(train_rows)}   validation examples: {len(val_rows)}")

    def encode(rows):
        feats = [tokenize_for_training(tokenizer, r["prompt"], r["completion"], args.max_len) for r in rows]
        return feats

    train_feats, val_feats = encode(train_rows), encode(val_rows)
    lengths = [len(f["input_ids"]) for f in train_feats]
    truncated = sum(1 for r, f in zip(train_rows, train_feats) if len(f["input_ids"]) >= args.max_len)
    print(f"Token length: mean {sum(lengths) / len(lengths):.0f}, max {max(lengths)}; "
          f"{truncated} example(s) hit the {args.max_len}-token limit")

    class ListDataset(torch.utils.data.Dataset):
        def __init__(self, items):
            self.items = items

        def __len__(self):
            return len(self.items)

        def __getitem__(self, i):
            return self.items[i]

    # ---- model --------------------------------------------------------------
    # Load in float32 and let Trainer's fp16 autocast handle speed; this avoids
    # the common "Attempting to unscale FP16 gradients" error with LoRA on a T4.
    model = AutoModelForCausalLM.from_pretrained(args.base, torch_dtype=torch.float32)
    lora = LoraConfig(r=args.lora_r, lora_alpha=2 * args.lora_r, lora_dropout=0.05, bias="none",
                      task_type="CAUSAL_LM", target_modules=LORA_TARGETS)
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    # ---- training -----------------------------------------------------------
    # warmup as a whole number of steps (about 3% of training); the older
    # `warmup_ratio` argument was removed in newer transformers versions
    steps_per_epoch = -(-len(train_rows) // (args.batch * args.grad_accum))
    warmup_steps = max(1, int(0.03 * steps_per_epoch * args.epochs))
    kwargs = dict(
        output_dir=os.path.join(args.out, "_trainer"),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch,
        per_device_eval_batch_size=args.batch,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_steps=warmup_steps,
        logging_steps=10,
        save_strategy="no",
        fp16=has_gpu,
        report_to="none",
        remove_unused_columns=False,
        seed=args.seed,
    )
    # the name of this argument changed between transformers versions
    sig = inspect.signature(TrainingArguments.__init__).parameters
    kwargs["eval_strategy" if "eval_strategy" in sig else "evaluation_strategy"] = "epoch"
    # drop any setting this transformers version no longer accepts, instead of crashing
    dropped = [k for k in kwargs if k not in sig]
    if dropped:
        print(f"Note: ignoring settings not supported by this transformers version: {dropped}")
    kwargs = {k: v for k, v in kwargs.items() if k in sig}

    trainer = Trainer(
        model=model,
        args=TrainingArguments(**kwargs),
        train_dataset=ListDataset(train_feats),
        eval_dataset=ListDataset(val_feats),
        data_collator=DataCollatorForSeq2Seq(tokenizer, padding=True, label_pad_token_id=-100),
    )
    start = time.time()
    trainer.train()
    minutes = (time.time() - start) / 60
    final_eval = trainer.evaluate()

    # ---- save ---------------------------------------------------------------
    os.makedirs(args.out, exist_ok=True)
    model.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)
    with open(os.path.join(args.out, "training_log.json"), "w") as f:
        json.dump({
            "base": args.base,
            "train_examples": len(train_rows),
            "val_examples": len(val_rows),
            "epochs": args.epochs,
            "minutes": round(minutes, 1),
            "final_eval": final_eval,
            "log_history": trainer.state.log_history,
        }, f, indent=2)
    print(f"\nDone in {minutes:.1f} min. Final validation loss: {final_eval.get('eval_loss'):.4f}")
    print(f"Adapter saved to: {args.out}")


if __name__ == "__main__":
    main()
