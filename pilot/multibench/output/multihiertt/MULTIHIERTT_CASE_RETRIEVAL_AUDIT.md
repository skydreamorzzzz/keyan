# MultiHiertt Case Retrieval Audit

Date: 2026-08-17

Scope: train-only Case Memory plus retrieval-only validation audit. No LLM/API calls, no Strategy Memory, no four-arm experiment, no router.

## Case Memory

- Source split: MultiHiertt train only.
- Cases: 7830 = program 6306 + span 1524.
- Each case stores question, answer, original program or span answer, gold text/table evidence, table hierarchy as raw HTML, table descriptions, operator sequence/family, and source_id.
- Unique source ids: 1814.
- Full case memory is local-only because raw HTML tables make it too large for normal GitHub commits: `data/multihiertt/processed/multihiertt_case_memory_train.json`.

## Retrieval Safety

- Target retrieval text uses only inference-visible fields: question, visible paragraphs, visible hierarchical HTML table previews, and visible table cell descriptions.
- Target retrieval text does not use gold answer, program, text evidence, table evidence, answer type, or operator family.
- Case retrieval text uses solved-case question plus historical gold evidence context. It does not use the case answer/program as retrieval text.
- Post-hoc compatibility metrics below use gold fields only after retrieval for diagnostics.

## Retrieval Setup

- Retriever: `BAAI/bge-small-en-v1.5` on `cpu`.
- Top-k: 4.
- Tuning: none.
- Source exclusion: same source_id skipped during retrieval.
- Source leak count after exclusion: 0.

## Source / Duplicate Document Audit

- Source id definition: `md5(json({paragraphs, tables}, sort_keys=True))`.
- Train unique sources: 1814.
- Validation unique sources: 280.
- Train-validation overlapping sources: 1 source(s), covering 3 validation question(s) and 1 train case(s).
- Fixed audit sample targets with train source overlap: 0.
- The dataset lacks explicit report/document ids in the parquet release, so document-hash source exclusion is the current leakage guard.

## Fixed Validation Audit

- Validation sample size: 120 fixed by seed `20260817`.
- Average top-1 score: 0.8678.
- Average retrieved score across top-4: 0.8593.
- Top-1 score range: 0.8036 to 0.9299.

| Diagnostic label | Top-1 match | Any top-4 match |
|---|---:|---:|
| `answer_type` | 0.817 | 0.875 |
| `operator_family` | 0.150 | 0.433 |
| `evidence_modality` | 0.300 | 0.592 |

Target distribution in fixed validation sample:

- answer_type: `{'program': 100, 'span': 20}`
- operator_family: `{'add': 31, 'divide+subtract': 30, 'span_lookup': 20, 'divide': 9, 'add+divide': 8, 'add+divide+multiply+subtract': 5, 'subtract': 4, 'multiply': 4, 'add+subtract': 3, 'add+divide+subtract': 3, 'divide+multiply': 1, 'add+multiply': 1, 'multiply+subtract': 1}`
- evidence_modality: `{'text+table': 65, 'text': 17, 'table': 38}`

## Typical Successful Retrievals

### multihiertt:validation:c30b113fd95f469682ac8ab0e07c7a1e

Question: What is the average value of Total net revenue for Reported Results, Fully taxable-equivalent adjustment, and Managed basis ? (in million)

Target labels: answer_type=`program`, operator_family=`add+divide`, evidence_modality=`text+table`.

| Rank | Score | Case question | Answer type | Operator family | Evidence modality |
|---:|---:|---|---|---|---|
| 1 | 0.8885 | What's the average of the Total revenue for Summary of Operations in the years where Mortgage-Backed Securitizations (c) for PNC Riskof Loss (a) is po | `program` | `add+divide` | `text+table` |
| 2 | 0.8786 | in 2006 what was the ratio of the increase in tax payments in 2005 and 2006 to the decrease in cash | `program` | `divide` | `text` |
| 3 | 0.8696 | what is the total amount paid in cash related to restructuring initiatives for the last three years? | `program` | `add` | `text` |
| 4 | 0.8650 | What was the average value of Net income (loss) from discontinued operations, Net income (loss), Net income (loss) from continuing operations in 2011? | `program` | `add+divide+subtract` | `table` |

### multihiertt:validation:a7a7582206944c1b8ed6be7bbc05336b

Question: What is the sum of Unrecognized net loss CHANGE IN PLAN ASSETS of CECONY 2015, Operating earnings of 2008, and FUNDED STATUS CHANGE IN PLAN ASSETS of Con Edison 2014 ?

Target labels: answer_type=`program`, operator_family=`add`, evidence_modality=`text+table`.

| Rank | Score | Case question | Answer type | Operator family | Evidence modality |
|---:|---:|---|---|---|---|
| 1 | 0.8794 | What's the sum of Granted of Con Edison Units, FUNDED STATUS CHANGE IN PLAN ASSETS of Con Edison 2014, and FUNDED STATUS CHANGE IN PLAN ASSETS of CECO | `program` | `add` | `text+table` |
| 2 | 0.8766 | What is the sum of FUNDED STATUS CHANGE IN PLAN ASSETS of CECONY 2010, Capital Expenditures on a GAAP Basis of 2016, and FAIR VALUE OF PLAN ASSETS AT  | `program` | `add` | `text+table` |
| 3 | 0.8679 | What is the sum of 2300 Discovery Drive, Orlando, Florida of Occupied Square Footage, Prepaid pension cost of Con Edison of New York 2004, and Actual  | `program` | `add` | `text+table` |
| 4 | 0.8646 | What will Asset retirement obligations in terms of Con Edison reach in 2015 if it continues to grow at its current rate? (in million) | `program` | `add+divide+multiply+subtract` | `text+table` |

### multihiertt:validation:2c5ade1a88b84b07b6e534a544862161

Question: Does the average value of Loans and leases in 2014 greater than that in 2013

Target labels: answer_type=`span`, operator_family=`span_lookup`, evidence_modality=`text+table`.

| Rank | Score | Case question | Answer type | Operator family | Evidence modality |
|---:|---:|---|---|---|---|
| 1 | 0.8674 | At December 31,what year is the proportion of the Tier 2 risk-based capital in terms of Bank in relation to the Total risk-based capital in terms of B | `span` | `span_lookup` | `text+table` |
| 2 | 0.8651 | What is the proportion of RiverSource Life in Actual Capital to the total in 2011? | `program` | `add+divide` | `text+table` |
| 3 | 0.8606 | in billions , what was the total for 2015 and 2014 relating to commitments to invest in funds managed by the firm? | `program` | `add` | `text` |
| 4 | 0.8579 | in 2006 what was the ratio of the class a shares and promissory notes international paper contributed in the acquisition of borrower entities interest | `program` | `divide` | `text` |

## Typical Failure Modes

### multihiertt:validation:6e69e996da0a482b87e237352da9369b

Question: What is the sum of Investment real estate in 2012 and Gain (loss) recognized in OCI on derivatives in 2011? (in million)

Target labels: answer_type=`program`, operator_family=`subtract`, evidence_modality=`text+table`.

| Rank | Score | Case question | Answer type | Operator family | Evidence modality |
|---:|---:|---|---|---|---|
| 1 | 0.8790 | In the year with less amount of Issuance proceeds, what's the sum of Commercial mortgage backed securities in 2010? | `program` | `add+subtract` | `text+table` |
| 2 | 0.8738 | What's the total amount of Private equity, Real estate, Distressed credit/mortgage funds and Hedge funds/funds of hedge funds in 2012? (in million) | `program` | `add` | `text+table` |
| 3 | 0.8646 | What was the total amount of the Low income housing tax credit funds in the years where Other venture capital investments -2 greater than 0? (in thous | `program` | `add` | `text+table` |
| 4 | 0.8637 | what was the ratio of the pension trust assets for 2017 to 2016 $ 1739 million and $ 1632 | `program` | `divide` | `text` |

### multihiertt:validation:faac106d01bb414e8459e88d762e51b4

Question: What's the greatest value of Stores Opened in 2011?

Target labels: answer_type=`span`, operator_family=`span_lookup`, evidence_modality=`text+table`.

| Rank | Score | Case question | Answer type | Operator family | Evidence modality |
|---:|---:|---|---|---|---|
| 1 | 0.8870 | what is the total amount paid in cash related to restructuring initiatives for the last three years? | `program` | `add` | `text` |
| 2 | 0.8787 | in 2006 what was the ratio of the increase in tax payments in 2005 and 2006 to the decrease in cash | `program` | `divide` | `text` |
| 3 | 0.8706 | what is the annual amortization expense related to bgi transaction of 2009 under a straight-line amortization method , in millions? | `program` | `divide` | `text` |
| 4 | 0.8687 | as part of the july 2011 acquisition of the property what was the percent of the assumed loan to the purchase price | `program` | `divide` | `text` |

### multihiertt:validation:776342a2d8c1492286eedc213289f373

Question: In the year with the most Granted for shares(in thousands), what is the growth rate of Outstanding ? (in %)

Target labels: answer_type=`program`, operator_family=`divide+subtract`, evidence_modality=`text+table`.

| Rank | Score | Case question | Answer type | Operator family | Evidence modality |
|---:|---:|---|---|---|---|
| 1 | 0.8869 | operating expenses were what multiple of pre-tax earnings in 2015? | `program` | `divide` | `text` |
| 2 | 0.8759 | what is the annual amortization expense related to bgi transaction of 2009 under a straight-line amortization method , in millions? | `program` | `divide` | `text` |
| 3 | 0.8664 | what was the percent of the share under this new share repurchase program as of december 312015 | `program` | `divide` | `text` |
| 4 | 0.8661 | In the year with less amount of Issuance proceeds, what's the sum of Commercial mortgage backed securities in 2010? | `program` | `add+subtract` | `text+table` |

## Interpretation

The retrieval layer is usable as a frozen diagnostic baseline if downstream work treats compatibility as post-hoc audit only. The most important caveat is source provenance: the parquet release lacks explicit report ids, so source exclusion relies on deterministic document hashes over paragraphs and HTML tables.

Decision: `READY FOR STRATEGY DESIGN`.
