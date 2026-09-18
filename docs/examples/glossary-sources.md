# Example glossary provenance and scope

`glossary-en-de.json` contains 36 manually selected rules. Its filename is reusable
across documents; its current vocabulary is primarily ML/AI, not a universal
English/German dictionary. Source review date: 2026-09-18. German targets and the
keep/translate/annotate policy are project editorial choices. Terminology review
does not establish that Marian preserves placeholders or grammatical agreement.

The [Google Machine Learning Glossary](https://developers.google.com/machine-learning/glossary)
and its [German edition](https://developers.google.com/machine-learning/glossary?hl=de)
provide conceptual cross-checks for these groups:

| Entries covered | Reference concepts |
| --- | --- |
| Classification, binary/multiclass classification | Classification tasks and number of classes |
| Supervised, unsupervised, reinforcement, machine and deep learning | Learning paradigms |
| Neural network(s), decision tree(s), clustering | Model families and grouping |
| Training/labeled/test/validation data and training/test datasets | Dataset roles |
| Learning rate, loss function, gradient descent, overfitting, underfitting | Optimization and generalization |
| Generative AI, embedding(s), fine-tuning, inference, large language model(s), LLM | Generation and model use |
| Retrieval-Augmented Generation (RAG), RAG, document retrieval | Retrieval-augmented generation |

No definitions, example passages, or bulk terminology exports are included.
Singular/plural entries are explicit because the matcher does not infer inflection.
Original English terminology is included in most targets; short established terms
such as embeddings remain English. Generic ambiguous words such as `policy`,
`class`, or `model` are intentionally excluded from fixed replacement rules.

`Klassifikation` is our selected variant rather than requiring the reference's
particular German wording. The RAG and LLM expansion entries implement the project's
abbreviation policy. Standalone RAG and LLM are preserved without inventing an
expansion absent from the input. Fixed German forms can still be wrong for a
sentence's grammatical case; review the result in context.

For future IT terminology, [Microsoft Terminology](https://learn.microsoft.com/en-us/globalization/reference/microsoft-terminology)
offers search and TBX downloads. [IATE](https://iate.europa.eu/home) covers EU
terminology across fields. Neither collection has been imported. Any future bulk
import should record the dataset version, domain selection, applicable reuse
terms, and attribution separately from doc-lingo's code license.
