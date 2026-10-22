# future_work: LoRA fine-tuning (not used in the final results)

`train_lora.py` and `colab_train.ipynb` implement the original plan: fine-tune
Qwen2.5-Coder-0.5B-Instruct with LoRA on the dataset in `dataset/out/` and
compare it with the un-tuned model.

**Status: written but never completed.** The GPU run could not be finished, so
nothing in the reported results depends on this folder, and the code has never
trained a model end to end. It is kept as documented future work. The dataset,
prompt format, verifier and evaluation scripts it relies on are the same ones
the final methods use, so it can be resumed later:

    python future_work/train_lora.py --batch 1 --grad-accum 16 --out mcl_adapter
    python evaluate_model.py --backend hf --adapter mcl_adapter --label finetuned --limit 100 --out results/finetuned.json
