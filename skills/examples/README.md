# NeuralCleave Community Skills

Example skills that extend NeuralCleave. Each file is a self-contained Python skill ready to install.

## Install a skill

```bash
cp weather.py ~/.neuralcleave/skills/
```

NeuralCleave hot-reloads the skill within seconds — no restart required.

## Skill format

Every skill needs:
1. A `SKILL_METADATA` dict with at least `name` and `description`
2. An `async def run(args: dict) -> str` function

## Contributing

1. Add your `.py` file to this directory following the existing skill format
2. Open a PR — it will appear on the [Skills Gallery](https://neuralcleave.com/docs/skills-gallery) after merge
