# Multi-Benchmark Financial Memory Study: Design Note

Date: 2026-08-16

Scope: design only. No API calls, no benchmark execution, no router optimization.

## 1. Benchmark Inventory

### FinQA

Current repo status: already integrated under `data/finqa/`, with official-compatible program execution in `pilot/executor.py`.

- Splits: train 6,251 / dev 883 / public test 1,147 / private test 919 question-only.
- Unit of example: one financial report page plus one question.
- Context: `pre_text`, `post_text`, one table (`table`, `table_ori`).
- Reasoning annotation: `qa.program`, `qa.program_re`, `qa.steps`, `qa.gold_inds`, `qa.exe_ans`.
- Task type: mostly numerical program generation over table/text; some `greater` yes/no.
- Existing memory fit: strongest fit. Current Case Memory and Strategy Memory were built around FinQA's program DSL and supporting facts.

### TAT-QA

Source checked: official TAT-QA site and public schema examples.

- Splits: train 13,215 questions / dev 1,668 / test 1,669, across 2,201 / 278 / 278 hybrid contexts.
- Unit of raw file: one hybrid context with `table`, `paragraphs`, and a list of `questions`.
- Context: one semi-structured table plus multiple paragraphs.
- Question fields: `uid`, `order`, `question`, `answer`, `derivation`, `answer_type`, `answer_from`, `rel_paragraphs`, `req_comparison`, `scale`; common processed versions may also expose `tree_derivation`, `facts`, `consts`, and mappings.
- Task types: span, multi-span/spans, arithmetic, counting; table-only, text-only, and table-text.
- Reasoning annotation: derivation string for arithmetic/counting, scale, answer type, answer source, supporting paragraphs/cells where available.
- Integration priority: first new dataset to add. It is closest to FinQA in financial hybrid table/text reasoning but differs by having non-program span/counting questions and explicit answer scale.

### MultiHiertt

Source checked: ACL 2022 paper summary and HuggingFace schema for a cleaned repackaging.

- Splits commonly available: train 7,830 / validation 1,044 with gold; reference-free test 1,566 is question-only in some releases.
- Unit of example: one document with multiple hierarchical tables and surrounding text.
- Context: `paragraphs` with `## Table N ##` placeholders, `tables` as HTML strings, `table_description` mapping cell ids to natural-language descriptions.
- Question fields: `uid`, `question`, `answer`, `program`, `text_evidence`, `table_evidence`.
- Task types: arithmetic program generation and direct span selection. About one release reports empty `program` for span questions.
- Reasoning annotation: FinQA-like flat DSL with `#N` references and `const_*`, plus text/table evidence.
- Key difference: multiple hierarchical tables make retrieval and context rendering more central than in FinQA/TAT-QA.

### ConvFinQA

Source checked: official ConvFinQA GitHub README.

- Conversation-level splits: train 3,037 / dev 421 / test 434 conversations.
- Turn-level splits: train_turn 11,104 / dev_turn 1,490 / test_turn 1,521 turns.
- Unit of raw file: either full conversation or individual turn.
- Context: inherited FinQA-like `pre_text`, `post_text`, `table`, `id`.
- Conversation annotation: `dialogue_break`, `turn_program`, `qa_split`, `exe_ans_list`; Type I decomposes one FinQA question, Type II combines two FinQA questions.
- Turn-level fields: `cur_program`, `cur_dial`, `exe_ans`, `cur_type`, `turn_ind`, `gold_ind`.
- Task type: conversational numerical reasoning with question history; current turn may be number selection or program.
- Leakage caveat: ConvFinQA is derived from FinQA. It must not be treated as an independent benchmark for transfer claims without source-id/report overlap controls.

Sources:

- FinQA local audit: `analysis/stage1_report.md`
- TAT-QA official format: https://nextplusplus.github.io/TAT-QA/
- MultiHiertt cleaned schema: https://huggingface.co/datasets/bevaya/MultiHiertt
- ConvFinQA official README: https://github.com/czyssrs/ConvFinQA

## 2. Unified Intermediate Format

Use one JSONL record per answerable query. For TAT-QA context-level files, flatten each question into a separate record. For ConvFinQA, use turn-level records for main experiments and keep conversation-level metadata.

```json
{
  "uid": "dataset:split:native_id[:turn]",
  "dataset_id": "finqa|tatqa|multihiertt|convfinqa",
  "split": "train|dev|test|validation",
  "source_id": "report/document/conversation id",
  "source_family": {
    "company": null,
    "year": null,
    "report_group": null,
    "finqa_origin_id": null
  },
  "question": "...",
  "dialogue_history": [],
  "context": {
    "pre_text": [],
    "post_text": [],
    "paragraphs": [],
    "tables": [
      {
        "table_id": "0",
        "format": "matrix|html|cell_descriptions",
        "content": "... or [][]",
        "cell_descriptions": {}
      }
    ],
    "rendered_context": "canonical prompt-ready text"
  },
  "reasoning": {
    "answer_type": "program|arithmetic|span|multi_span|count|yes_no|number_selection|unknown",
    "program": null,
    "program_dsl": "finqa|tatqa_derivation|multihiertt|none",
    "derivation": null,
    "operator_sequence": [],
    "operands": [],
    "n_steps": null,
    "evidence": {
      "text": [],
      "table": [],
      "paragraph_ids": [],
      "cell_ids": []
    }
  },
  "answer": {
    "value": "...",
    "exe_value": null,
    "scale": "",
    "unit": null,
    "normalized_value": null
  },
  "memory_metadata": {
    "case_allowed": true,
    "strategy_allowed": true,
    "source_leakage_group": null
  }
}
```

Design choices:

- Keep raw annotations and a normalized view. Do not force all datasets into FinQA's DSL at ingestion time.
- `program` is nullable because TAT-QA span/count and MultiHiertt span questions may not have executable programs.
- `operator_sequence` and `n_steps` should be derived where possible, but marked `null` for non-executable annotations.
- `source_leakage_group` is mandatory for FinQA/ConvFinQA provenance controls.

## 3. Memory Migration

### Case Memory

Case Memory can generalize across all four datasets if it stores a solved query plus its source-local context and answer path.

Dataset-specific treatment:

- FinQA: existing schema works directly.
- TAT-QA: store table, relevant paragraphs, answer type, scale, derivation/tree, and evidence mappings. Cases should include non-arithmetic span/count examples because they test whether memory helps answer-form selection.
- MultiHiertt: store document-level rendered context, table descriptions, evidence cells, and program/span label. Retrieval should include document/table hierarchy metadata.
- ConvFinQA: store turn-level cases with dialogue history. Also store conversation-level source id and original FinQA ids when available.

Case retrieval should index:

- question text;
- rendered evidence/context slice;
- answer type;
- operator sequence / derivation shape;
- scale and unit;
- dataset id and source group.

### Strategy Memory

Strategy Memory should become dataset-agnostic at the top level:

```json
{
  "strategy_id": "...",
  "scope": "program|span|count|conversation_followup",
  "operator_template": "...",
  "role_bindings": {},
  "answer_form": "numeric|span|multi_span|count|yes_no",
  "scale_convention": "...",
  "evidence_pattern": "table|text|table-text|multi-table|dialogue",
  "source_datasets": [],
  "example_case_ids": [],
  "caveats": []
}
```

Migration expectations:

- FinQA strategies transfer best to TAT-QA arithmetic and MultiHiertt program questions.
- FinQA strategies transfer weakly to TAT-QA span/count and ConvFinQA number-selection turns unless strategy scope is expanded.
- TAT-QA contributes answer-form and scale strategies that FinQA lacks.
- MultiHiertt contributes multi-table/hierarchical evidence strategies.
- ConvFinQA contributes follow-up resolution strategies: ellipsis, previous-turn operands, and turn-local vs dialogue-global state.

## 4. Experiments

### A. Memory Transfer

Question: does memory built from dataset A help dataset B?

Arms, fixed within each target dataset:

- None
- Case from target train
- Strategy from target train
- Case from source dataset A
- Strategy from source dataset A
- Case+Strategy source
- optional mixed source+target, only after single-source transfer is understood

Evaluation:

- use each dataset's official answer metric first;
- for program-compatible subsets, also report execution accuracy;
- report by answer type/operator family/evidence source/scale;
- hold out test until ingestion and dev analyses are stable.

Critical controls:

- no target dev/test examples in memory;
- no same report/document/conversation in memory;
- for FinQA ↔ ConvFinQA, block shared original FinQA source ids and report groups;
- report same-company and cross-company slices separately where company/year can be parsed.

### B. Router Transfer

Question: can memory utility learned on A/B/C predict whether to deviate from default memory action on D?

Default action should be dataset-specific:

- FinQA: current evidence says Both is strongest fixed action under the existing prompt.
- TAT-QA: do not assume Both; establish fixed arms first.
- MultiHiertt: likely context budget makes memory-cost tradeoff central.
- ConvFinQA: dialogue memory may be a separate default from cross-sample experience memory.

Router target:

```text
delta_a = E[correct(a) - correct(default)]
```

where `a` can be None, Case, Strategy, or source-specific memory variants.

Transfer setup:

- train selector on A/B/C dev or train-heldout utility labels;
- evaluate once on D dev/test split;
- use grouped CV by report/document/conversation for development;
- never tune thresholds on target D test;
- report accuracy, memory tokens, deviation coverage, beneficial/harmful/neutral deviations, and cluster bootstrap by source document.

## 5. FinQA / ConvFinQA Leakage Policy

FinQA and ConvFinQA are not independent:

- ConvFinQA conversations are decompositions/combinations of FinQA questions.
- IDs and report pages overlap conceptually; Type I conversations come from one FinQA question, Type II from two.

Rules:

1. Build a `finqa_origin_id` map for ConvFinQA from `qa`, `qa_0`, `qa_1`, `original_program`, and native ids.
2. In FinQA → ConvFinQA memory transfer, exclude memory cases with the same FinQA origin id or same report group.
3. In ConvFinQA → FinQA transfer, exclude conversation turns derived from the target FinQA source.
4. Do not use FinQA/ConvFinQA as two independent training domains in leave-one-dataset-out claims unless overlap-filtered.
5. Report filtered and unfiltered numbers separately if both are computed; only filtered numbers support transfer claims.

## 6. Minimal Implementation Order

1. Add a lightweight `benchmarks/` or `pilot/multibench/` module with:
   - unified IR schema;
   - dataset adapters;
   - source-group extraction;
   - small schema audit scripts.
2. TAT-QA first:
   - download or point to local raw JSON;
   - flatten context-level records to query-level IR;
   - implement official answer/scale evaluation wrapper;
   - build TAT-QA Case Memory from train;
   - derive simple Strategy Memory from derivation/tree where available.
3. Run no-LLM ingestion checks:
   - counts per split;
   - answer type distribution;
   - scale distribution;
   - derivation parse coverage;
   - evidence availability.
4. Run tiny prompt dry-run only after ingestion is stable:
   - 20 TAT-QA dev examples;
   - None/Case/Strategy/Both;
   - manual error taxonomy, not performance claim.
5. Add MultiHiertt adapter:
   - handle HTML tables and `table_description`;
   - initially evaluate gold-label coverage and context length before LLM calls.
6. Add ConvFinQA adapter:
   - turn-level IR first;
   - implement FinQA-origin leakage map before any transfer experiment.
7. Only then define multi-benchmark transfer experiments and API budgets.

## 7. Immediate Next Step

Implement TAT-QA ingestion plus audit only:

```text
raw TAT-QA JSON -> unified IR JSONL -> split/count/type/scale/derivation report
```

Do not start memory-transfer execution until the adapter, evaluator, and leakage grouping are verified.
