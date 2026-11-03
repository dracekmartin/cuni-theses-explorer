# 0005: Batch jobs on the faculty cluster

Date: 2026-11-02. Status: accepted. Supersedes the point of
[0002](0002-containerization.md) that all batch steps run as compose commands.

## Context

The whole university is about 30 million passages at the current chunking. Embedding them
takes over 100 hours on the notebook GPU, and the serving node is not known yet. The MFF
HPC cluster has GPU nodes (A100, H100, L40) and schedules jobs with SLURM. It has no
Docker: the gpulab nodes offer Podman and Charliecloud, and the Chimera cluster, which has
GPU nodes as well, offers Apptainer. Jobs have time limits from 12 hours to 7 days and can
be preempted and requeued. MetaCentrum is the alternative, with PBS instead of SLURM.

Decision 0002 runs batch steps as one-off compose commands against the same database
service. A cluster job cannot reach the database of the serving node, and pgvector cannot
build its HNSW index on a GPU. A built index moves between machines only as a copy of the
whole PostgreSQL data directory, which would also replace the catalog and the caches of
the serving node.

## Decision

- Heavy batch work runs as jobs on the faculty cluster: bulk embeddings and other data for
  full index builds, evaluation runs at full scale and builds of the topic map. MetaCentrum
  is the fallback with the same jobs.
- The jobs run the same container images as the rest of the system, under Podman on the
  gpulab nodes or as an Apptainer image converted from them.
- A job writes its results as files: vectors in shards with a manifest (model, revision,
  snapshot, counts). The batch tools on the serving node import the vectors together with
  the manifest, and the database there builds the index over them. The files stay as the
  source for a repeated import. A data directory is never copied, because it would replace
  the catalog and the caches of the serving node.
- Every job can be stopped and started again and continues where it stopped, because the
  cluster may preempt it.
- Light batch work stays on the serving node as in 0002: synchronization with DSpace,
  chunking, incremental index updates, imports. Cron starts it.

## Consequences

- The images must not rely on features only Docker has, so that Podman and Apptainer can
  run them.
- The serving node needs the memory and the time to build the vector index. For 30 million
  passages in half precision that is an estimated 80 GB of maintenance memory for
  PostgreSQL and several hours. Quantization or a smaller index lowers it, which is
  a decision still to come.
- Thesis texts have to be stored on the cluster during a job. Whether they may stay in its
  `/work` storage is still to be asked.
- Job state must be kept per shard of the corpus, so that a requeued job does not start
  from the beginning.

## Alternatives considered

- **Everything on the serving node.** Simplest, but needs a large GPU there, and the node
  is not known.
- **Only MetaCentrum.** Larger and documented, but the account has to be renewed every
  year and the scheduler is PBS. It stays as the fallback.
- **Embeddings through e-INFRA.** Ruled out by [0004](0004-models-at-query-time.md):
  corpus embeddings come only from models whose weights the project holds.
