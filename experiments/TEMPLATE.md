# Experiment NN: short name

<!-- Copy this file to experiments/NN-name/README.md and replace the comments.
     Keep the section order, so that experiments read and compare the same way. -->

<!-- The question this experiment answers, in one or two sentences. -->

| | |
| --- | --- |
| Status | planned, running or done |
| Date | date of the findings, YYYY-MM-DD |
| Builds on | experiment NN, or none |
| Corpus | eval/vN (N theses, harvested YYYY-MM-DD), or a description of an own sample |
| Queries | eval/vN, or ad hoc queries listed under Results |
| Hardware | for example laptop, RTX 4050 6 GB |
| Feeds | open question N in docs/architecture.md, or a decision record |

## Pipeline

<!-- One row per stage, named as in docs/architecture.md. The last column says what
     changed against the experiment this one builds on; leave it empty when nothing did.
     A setup that skips a stage says "not used". An experiment that builds no search
     setup replaces this section with a description of its procedure. When the
     experiment compares several setups, describe the shared baseline here and list the
     setups under Results. -->

| Stage | Setting | Change |
| --- | --- | --- |
| Harvest | | |
| Text extraction | | |
| Chunking | | |
| Embedding | | |
| Lexical branch | | |
| Search strategy | | |
| Reranking | | |
| Aggregation to theses | | |

## Outputs

<!-- What the scripts produce and where: data under data/NN-name/, runs under
     data/runs/NN-name/, results under results/. -->

## Results

<!-- Metrics come from eval/score.py, never from code in this experiment. Paste the
     table printed by eval/compare.py, with significant differences marked. Add the cost
     (indexing time, index size, query latency) and the top results of the showcase
     queries from experiments/README.md. -->

## Findings

<!-- Dated paragraphs: what the experiment showed, with numbers. -->

## Reproduce

<!-- Commands, run from the repository root. -->

## Next

<!-- Open questions the experiment raised. -->
