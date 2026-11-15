# Use of AI in this project

NASA Space Apps asks every team to say where and how AI tools were used. This is our statement.

## The tool

Two AI tools were used.

- **Claude** (Anthropic), through Claude Code. It worked inside this project folder, under the team's direction, during the preparation and the hackathon weekend (November 2026).
- **Google Flow**, for three decorative pictures on the website.

## What the assistant did

| Part of the project | How AI was used |
|---|---|
| **Code** (`build/`, `engine/`, `contract/make_examples.py`) | Written with the assistant. The team ran it, checked the outputs and decided what to keep. |
| **Tests and validation** (`engine/tests*.py`, `engine/test_api.py`, `build/cube_validate.py`) | Written with the assistant, from test specifications the team approved. |
| **Documents** (`README.md`, `VARIABLES.md`, `SOURCES.md`, `docs/*.md`, the method specification) | Drafted with the assistant and reviewed by the team. |
| **Figures and maps** (`docs/figures/`, `runs/*/*.png`, `export/`) | Drawn by code from the data. The code was written with the assistant. |
| **Website** (`website/`) | Code and text written with Claude, under the team's direction. |
| **Three pictures on the website** (`website/img/hero.jpg`, `globe-moon.png`, `globe-mars.png`) | Made with Google Flow. They are decoration only and carry a visible "AI-generated" mark. |
| **Slides and pitch text** | Drafted with the assistant and edited by the team. |

## What the team did

- Chose the challenge and the targets (NASA's own Artemis III regions and Mars Exploration Zones).
- Made every method decision. The assistant proposed options with measurements and a recommendation. The team chose, and in several cases chose against the recommendation. Each decision is dated in `VARIABLES.md`.
- Chose the data sources and checked them against the original publications.
- Ran the pipeline, read the results and decided what they mean.

## What AI was not used for

- **No AI-generated maps, charts, video or audio.** Every map and figure is computed from public data. The only AI-generated images are the three decorative website pictures named above. Photos in the slides are NASA's and carry a credit; the slides hold no AI-generated image.
- **No AI-generated data.** Every number comes from the public datasets listed in `SOURCES.md`, through the code in this repository.
- **No AI-written results.** Scores, ranks and p-values are outputs of `engine/`, with fixed random seeds, and can be recomputed.

## Where it is marked

- This file and the "AI use" section of `README.md`.
- The "Use of AI" note on the website's home page and in `website/README.md`, and the mark on the three pictures.
- The method specification, section 16.
- Git history: commits made with the assistant carry a `Co-Authored-By: Claude` line.
- The closing slide of the project demo.

## Limits of this statement

The assistant can be wrong. Where it was, the correction is recorded in `VARIABLES.md` and struck through there, not deleted.
