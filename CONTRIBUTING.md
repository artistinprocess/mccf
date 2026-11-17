# Contributing to MCCF

Thank you for looking. A fresh pair of eyes finds what the authors cannot.
The test for every change is the ecosystem rule: does it make MCCF easier and
more transparent to improve, and to improve other systems with?

## Report a problem
Please include:
- the repository commit (`git rev-parse HEAD`) and whether you changed anything,
- your operating system and browser,
- the LLM provider, model and settings, if an LLM was involved,
- the steps, what you expected and what happened, and the browser console log.

Never post API keys or other secrets. Redact them first.

## Run a reproducible trial
- Pin a commit, keep the original untouched and work in a separate copy.
- Record three things separately: (1) model output (model, prompt, response,
  latency, errors), (2) MCCF state transitions (events, requested and applied
  changes, bounds), (3) scene presentation (staging, timing, assets).
- Say which tests are component tests, integration tests, or complete
  narrative-use tests. Hold everything constant except the one thing you vary.
- Say plainly what your numbers show and what they do not show.

## Change the code
- Fix the cause, not the symptom. Prefer fixing code over adding an alias.
- Metres everywhere. Never shift the XYZ origin.
- Keep changes small, mark the files you changed, and keep licence notices.
- Add or update a test, and describe how you ran it.
- Say which people and tools (including LLMs) helped. Paul Hugel's trial report
  is a good model for this.

## Write documentation
- Guide chapters, lessons and effect assemblies use S1000D-style data module
  codes. Use your own issuer letters (three to five letters) in the code, so two
  authors can never issue the same code. A code is never reused or renumbered.
- Write what to do and what the reader should see. A step ends with something the
  reader can check. Give troubleshooting entries a remedy.

## Licence of contributions
Unless you say otherwise, contributions are licensed as the project is: code and
schemas under Apache-2.0, documentation and images under CC BY 4.0.
