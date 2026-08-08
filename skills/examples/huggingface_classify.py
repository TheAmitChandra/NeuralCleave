SKILL_METADATA = {
    "name": "huggingface_classify",
    "description": "Zero-shot text classification using a local HuggingFace pipeline.",
    "version": "1.0.0",
    "trigger": "classify",
    "dependencies": ["transformers", "torch"],
}

from transformers import pipeline as hf_pipeline

_clf = None


async def run(args: dict) -> str:
    global _clf
    if _clf is None:
        _clf = hf_pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
    text = args.get("text", "")
    labels = args.get("labels", ["positive", "negative", "neutral"])
    if isinstance(labels, str):
        labels = [l.strip() for l in labels.split(",")]
    result = _clf(text, candidate_labels=labels)
    top = result["labels"][0]
    score = result["scores"][0]
    return f"Classification: {top} ({score:.1%} confidence)"
