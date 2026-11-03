workspace "Theses Explorer" "Hybrid search, topic map and AI overview over the theses of Charles University." {

    !identifiers hierarchical

    model {
        user = person "User" "Student, visitor or teacher."
        operator = person "Operator" "Library or faculty staff running the service."
        maintainer = person "Maintainer" "Developer or researcher evolving the system."

        apiClient = softwareSystem "API client" "Scripts and other tools using the public API." "External"
        explorer = softwareSystem "Theses Explorer" "Hybrid search, topic map and AI overview over the theses of Charles University." {
            group "Serving" {
                webUi = container "Web UI" "Search, thesis detail, topic map and overview in the browser. Pages for maintainers and operators are not linked from the public part." "TypeScript, React"
                proxy = container "Reverse proxy" "HTTPS with the server certificate, static files of the web UI, limits on requests per IP address." "nginx"
                api = container "API" "Public REST API with the search core, overview and explanations as a library inside. Sends the topic map as one cached response per map version. Limits for expensive endpoints." "Python, FastAPI, explorer_api" {
                    endpoints = component "Search endpoints" "REST endpoints for search and for the chunks that show why a thesis was found. Behind a login for maintainers: the list of setups, the choice of a setup, the trace." "FastAPI, explorer_api"
                    loader = component "Setup loader" "Reads the setup files at start, checks them against the registry and the index manifests, builds one searcher per setup." "explorer"
                    registry = component "Registry" "Named searchers, steps and model adapters with versions. Finds plugins by entry points." "explorer"
                    wrapper = component "Platform wrapper" "Runs around every searcher: query safety check, query analysis, filters the searcher lacks, visibility guard, chunks on request, trace, short result cache." "explorer"
                    safety = component "Query safety check" "Stops or limits a query that looks for problematic places in theses. Small checks chosen by configuration." "explorer"
                    guard = component "Visibility guard" "Drops theses that are not public now, chunks of older versions and body chunks of theses whose text was locked." "explorer"
                    pipeline = component "PipelineSearcher" "The default searcher. Runs the step tree of a setup." "explorer"
                    analyzer = component "Query analyzer" "Turns the query text into a query: language with confidence or no language, lemmas, embeddings." "explorer"
                    sources = component "Candidate sources" "Leaf steps: dense vectors, a lexical index or metadata chunks of one index build, or another searcher." "explorer"
                    ranking = component "Ranking steps" "Fusion, aggregation, passage selection, reranking, filters, routers." "explorer"
                    pluginSteps = component "Plugin steps" "Steps from installed plugins, anywhere in the tree: candidate sources with their own index, fusions, rerankers, routers." "plugin packages" "Plugin"
                    dspaceSearcher = component "DSpace searcher" "The whole search delegated to the search of DSpace. Searchers from other plugins take the same place." "explorer_dspace" "Plugin"
                    adapters = component "Model adapters" "HTTP adapters of EmbeddingProvider, SparseEncoder and Reranker." "explorer"
                    answerEndpoints = component "Overview and map endpoints" "REST endpoints for the overview, the explanation of a neighbor edge, the topic map of one version and the neighbors of a thesis." "FastAPI, explorer_api"
                    overview = component "Overview" "Answers a question from the theses the search found: selects chunks, lets an LLM write an answer with citations, keeps only verified claims." "explorer"
                    gates = component "Gates" "Small checks that let an overview through or stop it with a reason. The safety gate always runs." "explorer"
                    explanations = component "Explanations" "Explain what two neighboring theses share, from the stored chunk pairs of their edge." "explorer"
                    mapReader = component "Map reader" "Reads one version of the topic map and the neighbors of a thesis." "explorer"
                    llmAdapters = component "LLM adapters" "HTTP adapters of LLMProvider and Verifier." "explorer"
                }
                modelServer = container "Model server" "Query embeddings, reranking and sparse weights for the API, batch tools and evaluation, on a GPU or the CPU. Our own service over the in-process adapters by default, TEI or vLLM when throughput matters." "Python, FastAPI, explorer_models_local"
            }
            group "Data" {
                database = container "Database" "Catalog, chunks, indexes, map data and caches, one writer per schema." "PostgreSQL, pgvector" "Database"
                files = container "File storage" "Results of cluster jobs (vectors, map builds) with their manifests, kept for a repeated import, and PDFs for own text extraction. Used only by the batch tools." "File system" "Database"
            }
            group "Batch" {
                batchTools = container "Batch tools" "Synchronization with DSpace, chunking, index builds and imports, map builds. Started by cron on the serving node, heavy jobs on the cluster (SLURM) or MetaCentrum (PBS)." "Python, explorer_batch" {
                    commands = component "Batch commands" "CLI commands for synchronization, text extraction, chunking, index builds, cluster jobs and map builds. Cron starts the regular ones. Every run records its outcome." "explorer_batch"
                    harvester = component "Harvester" "Reads changed records from OAI-PMH and continues after a crash. Finds withdrawn records, which OAI does not mark." "explorer"
                    catalog = component "Catalog" "The only writer of the schema catalog: versions, metadata, access status, supervisors, twin groups, texts, runs of batch commands." "explorer"
                    extraction = component "Text extraction" "Takes the text file of DSpace, or extracts the text from the public PDF where that file is missing or empty. Cleans abstracts." "explorer"
                    chunker = component "Chunker" "The only writer of chunks. Splits texts and metadata into the chunks of one chunking and detects the language of each chunk." "explorer"
                    builders = component "Index builders" "Built-in builders of dense and lexical indexes. Each adds what changed since its last build and deletes its entries of versions that are gone." "explorer"
                    pluginBuilders = component "Plugin index builders" "Builders of the indexes that plugins bring, with the same contract." "plugin packages" "Plugin"
                    jobs = component "Cluster jobs" "Submit heavy jobs with their input, fetch their results as files with manifests, import them into the database." "explorer_batch"
                    mapBuilder = component "Map builder" "Builds thesis vectors, the neighbor graph and the topic map, on the serving node or as a cluster job." "explorer_map"
                    adapters = component "Model adapters" "The same HTTP adapters as in the API, for the embeddings and sparse weights of new chunks." "explorer"
                }
                evalTool = container "Evaluation tool" "Runs setups over an evaluation set on the notebook or as a job on the cluster, writes TREC runs and scores them." "Python, explorer_eval"
            }
        }
        dspace = softwareSystem "DSpace UK" "Digital repository of Charles University, DSpace 6.4." "External"
        einfra = softwareSystem "e-INFRA CZ" "Academic OpenAI-compatible LLM API." "External"
        batch = softwareSystem "Batch compute" "MFF HPC cluster (SLURM, GPU nodes) or MetaCentrum (PBS)." "External"

        user -> explorer "Searches theses, browses the topic map, reads AI overviews" "HTTPS"
        operator -> explorer "Checks synchronization runs" "HTTPS"
        maintainer -> explorer "Defines and compares setups, runs evaluations" "CLI, HTTPS"
        apiClient -> explorer "Searches theses" "HTTPS, JSON"
        explorer -> dspace "Harvests metadata, access status and texts, searches through it for comparison" "OAI-PMH, HTTPS"
        explorer -> einfra "Generates overviews and explanations, judges relevance in evaluation" "OpenAI API"
        explorer -> batch "Runs its heavy batch jobs there (bulk embeddings, evaluation runs, map builds), fetches the results as files" "SSH, SLURM or PBS"

        user -> explorer.webUi "Searches theses, browses the topic map, reads AI overviews" "HTTPS"
        operator -> explorer.webUi "Checks synchronization runs on the operator page" "HTTPS"
        maintainer -> explorer.webUi "Compares two setups on the hidden comparison page" "HTTPS"
        maintainer -> explorer.batchTools "Starts index builds and heavy jobs" "CLI"
        maintainer -> explorer.batchTools.commands "Starts commands by hand" "CLI"
        maintainer -> explorer.evalTool "Runs evaluations" "CLI"
        apiClient -> explorer.proxy "Calls the public API" "HTTPS, JSON"

        explorer.webUi -> explorer.proxy "Loads its files and calls the API" "HTTPS, JSON"
        explorer.proxy -> explorer.api "Forwards API requests" "HTTP"
        explorer.api -> explorer.database "Reads the catalog, indexes and artifacts, writes caches" "SQL"
        explorer.api -> explorer.modelServer "Embeds queries, reranks candidates" "HTTP"
        explorer.api -> dspace "Searches through DSpace for the DSpace setup" "HTTPS"
        explorer.api -> einfra "Generates overviews and explanations" "HTTPS, OpenAI API"
        explorer.batchTools -> dspace "Harvests metadata, access status, texts and PDFs" "OAI-PMH, HTTPS"
        explorer.batchTools -> explorer.database "Writes the catalog, imports index builds, writes artifacts" "SQL"
        explorer.batchTools -> explorer.files "Stores and reads job results, manifests and PDFs" "File system"
        explorer.batchTools -> batch "Submits heavy jobs, fetches their results as files" "SSH, SLURM or PBS"
        explorer.batchTools -> einfra "Labels the clusters of the topic map" "HTTPS, OpenAI API"
        explorer.batchTools -> explorer.modelServer "Embeds new theses" "HTTP"
        explorer.proxy -> explorer.api.endpoints "Forwards API requests" "HTTP"
        explorer.api.endpoints -> explorer.api.loader "Looks up the setup"
        explorer.api.endpoints -> explorer.api.wrapper "Runs the search, asks for chunks"
        explorer.api.loader -> explorer.api.registry "Resolves names of steps and searchers"
        explorer.api.loader -> explorer.database "Reads the manifests of index builds" "SQL"
        explorer.api.wrapper -> explorer.api.safety "Checks the query first"
        explorer.api.wrapper -> explorer.api.pipeline "Searches"
        explorer.api.wrapper -> explorer.api.dspaceSearcher "Searches"
        explorer.api.wrapper -> explorer.api.analyzer "Analyzes the query once"
        explorer.api.wrapper -> explorer.api.guard "Filters the results"
        explorer.api.wrapper -> explorer.api.ranking "Selects chunks of a thesis on request"
        explorer.api.wrapper -> explorer.database "Caches results for a few minutes" "SQL"
        explorer.api.guard -> explorer.database "Reads access status and versions" "SQL"
        explorer.api.pipeline -> explorer.api.sources "Runs built-in leaf steps"
        explorer.api.pipeline -> explorer.api.pluginSteps "Runs them like built-in steps"
        explorer.api.pipeline -> explorer.api.ranking "Runs the inner steps"
        explorer.api.analyzer -> explorer.api.adapters "Embeds the query"
        explorer.api.sources -> explorer.database "Searches index builds" "SQL"
        explorer.api.sources -> explorer.api.dspaceSearcher "Runs another searcher as a leaf"
        explorer.api.pluginSteps -> explorer.database "Search their index storage" "SQL"
        explorer.api.pluginSteps -> explorer.api.adapters "Call the models they need"
        explorer.api.ranking -> explorer.database "Reads chunks for passage selection" "SQL"
        explorer.api.ranking -> explorer.api.adapters "Reranks candidates"
        explorer.api.adapters -> explorer.modelServer "Calls the models" "HTTP"
        explorer.api.dspaceSearcher -> dspace "Searches DSpace" "HTTPS"
        explorer.proxy -> explorer.api.answerEndpoints "Forwards API requests" "HTTP"
        explorer.api.answerEndpoints -> explorer.api.overview "Asks for an overview"
        explorer.api.answerEndpoints -> explorer.api.explanations "Asks for an explanation"
        explorer.api.answerEndpoints -> explorer.api.mapReader "Asks for the map and neighbors"
        explorer.api.overview -> explorer.api.wrapper "Gets the results of the same search"
        explorer.api.overview -> explorer.api.gates "Checks before and after generation"
        explorer.api.overview -> explorer.api.adapters "Scores chunks with the reranker"
        explorer.api.overview -> explorer.api.llmAdapters "Generates the answer, verifies claims"
        explorer.api.overview -> explorer.database "Caches overviews" "SQL"
        explorer.api.explanations -> explorer.api.llmAdapters "Generates and verifies explanations"
        explorer.api.explanations -> explorer.database "Reads chunk pairs, caches explanations" "SQL"
        explorer.api.mapReader -> explorer.database "Reads artifacts" "SQL"
        explorer.api.mapReader -> explorer.api.guard "Hides theses withdrawn since the map build"
        explorer.api.explanations -> explorer.api.guard "Checks both theses first"
        explorer.api.llmAdapters -> einfra "Calls the LLM" "HTTPS, OpenAI API"
        explorer.batchTools.commands -> explorer.batchTools.catalog "Records every run"
        explorer.batchTools.commands -> explorer.batchTools.harvester "Runs synchronization"
        explorer.batchTools.commands -> explorer.batchTools.extraction "Runs text extraction"
        explorer.batchTools.commands -> explorer.batchTools.chunker "Runs chunking"
        explorer.batchTools.commands -> explorer.batchTools.builders "Runs index builds and updates"
        explorer.batchTools.commands -> explorer.batchTools.pluginBuilders "Runs them like built-in builders"
        explorer.batchTools.commands -> explorer.batchTools.jobs "Submits heavy jobs, imports their results"
        explorer.batchTools.commands -> explorer.batchTools.mapBuilder "Runs map builds"
        explorer.batchTools.harvester -> dspace "Harvests changed records, checks for withdrawn ones" "OAI-PMH, HTTPS"
        explorer.batchTools.harvester -> explorer.batchTools.catalog "Records new, changed and withdrawn versions"
        explorer.batchTools.extraction -> dspace "Downloads text files, and PDFs where needed" "HTTPS"
        explorer.batchTools.extraction -> explorer.files "Keeps downloaded PDFs" "File system"
        explorer.batchTools.extraction -> explorer.batchTools.catalog "Stores texts and abstracts"
        explorer.batchTools.catalog -> explorer.database "Writes the schema catalog" "SQL"
        explorer.batchTools.chunker -> explorer.database "Reads texts of changed versions, writes and deletes chunks" "SQL"
        explorer.batchTools.builders -> explorer.database "Reads changes and chunks, writes index builds" "SQL"
        explorer.batchTools.builders -> explorer.batchTools.adapters "Embeds chunks"
        explorer.batchTools.pluginBuilders -> explorer.database "Read changes and chunks, write their index storage" "SQL"
        explorer.batchTools.pluginBuilders -> explorer.batchTools.adapters "Call the models they need"
        explorer.batchTools.adapters -> explorer.modelServer "Calls the models" "HTTP"
        explorer.batchTools.jobs -> batch "Submits jobs, fetches their results" "SSH, SLURM or PBS"
        explorer.batchTools.jobs -> explorer.files "Stores results with manifests, reads them for import" "File system"
        explorer.batchTools.jobs -> explorer.database "Imports vectors, plugin indexes and map builds" "SQL"
        explorer.batchTools.mapBuilder -> explorer.database "Reads chunk vectors, writes artifacts" "SQL"
        explorer.batchTools.mapBuilder -> einfra "Labels the clusters of the topic map" "HTTPS, OpenAI API"
        explorer.evalTool -> explorer.database "Runs setups against the indexes" "SQL"
        explorer.evalTool -> einfra "Judges relevance" "HTTPS, OpenAI API"
        explorer.evalTool -> explorer.modelServer "Embeds queries, reranks candidates" "HTTP"
        explorer.evalTool -> dspace "Searches through DSpace for the DSpace setup" "HTTPS"
        explorer.evalTool -> batch "Runs evaluations at full scale as jobs" "SSH, SLURM or PBS"
    }

    views {
        properties {
            "c4plantuml.tags" "true"
        }

        systemContext explorer "context" {
            include *
            autoLayout lr
        }

        container explorer "containers" {
            title "Containers: overview"
            include *
            exclude "explorer.api -> dspace"
            exclude "explorer.evalTool -> dspace"
            exclude "maintainer -> explorer.webUi"
            exclude "explorer.evalTool -> batch"
            exclude "explorer.evalTool -> explorer.modelServer"
            exclude "explorer.batchTools -> einfra"
            exclude "explorer.evalTool -> einfra"
            autoLayout lr
        }

        container explorer "containers-serving" {
            title "Containers: serving queries"
            include user operator maintainer apiClient
            include explorer.webUi explorer.proxy explorer.api explorer.modelServer explorer.database
            include einfra dspace
            autoLayout lr
        }

        container explorer "containers-batch" {
            title "Containers: batch work"
            include maintainer
            include explorer.batchTools explorer.database explorer.files explorer.modelServer
            include dspace einfra batch
            autoLayout lr
        }

        component explorer.api "components-search" {
            title "Components: search in the API"
            include explorer.proxy explorer.database explorer.modelServer dspace
            include explorer.api.endpoints explorer.api.loader explorer.api.registry explorer.api.wrapper explorer.api.safety explorer.api.guard explorer.api.pipeline explorer.api.analyzer explorer.api.sources explorer.api.ranking explorer.api.pluginSteps explorer.api.dspaceSearcher explorer.api.adapters
            exclude "explorer.api.loader -> explorer.database"
            exclude "explorer.api.wrapper -> explorer.database"
            autoLayout lr
        }

        component explorer.api "components-overview" {
            title "Components: overview, explanations and map in the API"
            include explorer.proxy explorer.database explorer.modelServer einfra
            include explorer.api.answerEndpoints explorer.api.overview explorer.api.gates explorer.api.explanations explorer.api.mapReader explorer.api.llmAdapters explorer.api.wrapper explorer.api.guard explorer.api.adapters
            exclude "explorer.api.wrapper -> explorer.database"
            exclude "explorer.api.wrapper -> explorer.api.guard"
            exclude "explorer.api.guard -> explorer.database"
            autoLayout lr
        }

        component explorer.batchTools "components-sync" {
            title "Components: synchronization and texts"
            include maintainer explorer.database explorer.files dspace
            include explorer.batchTools.commands explorer.batchTools.harvester explorer.batchTools.catalog explorer.batchTools.extraction explorer.batchTools.chunker
            autoLayout lr
        }

        component explorer.batchTools "components-index" {
            title "Components: embeddings, index and map builds"
            include maintainer explorer.database explorer.files explorer.modelServer einfra batch
            include explorer.batchTools.commands explorer.batchTools.builders explorer.batchTools.pluginBuilders explorer.batchTools.jobs explorer.batchTools.mapBuilder explorer.batchTools.adapters
            autoLayout lr
        }

        container explorer "containers-evaluation" {
            title "Containers: evaluation"
            include maintainer
            include explorer.evalTool explorer.database explorer.modelServer
            include dspace einfra batch
            autoLayout lr
        }

        styles {
            element "Person" {
                shape Person
                background #08427b
                color #ffffff
            }
            element "Software System" {
                background #1168bd
                color #ffffff
            }
            element "Container" {
                background #438dd5
                color #ffffff
            }
            element "Component" {
                background #85bbf0
                color #000000
            }
            element "Plugin" {
                background #c9e1f7
                border dashed
            }
            element "Database" {
                shape Cylinder
            }
            element "External" {
                background #999999
                color #ffffff
            }
        }
    }
}
