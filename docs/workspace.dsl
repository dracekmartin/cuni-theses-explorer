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
                api = container "API" "Public REST API with the search core, overview and explanations as a library inside. Sends the topic map as one cached response per map version. Limits for expensive endpoints." "Python, FastAPI, explorer_api"
                modelServer = container "Model server" "Query embeddings, reranking and sparse weights for the API, batch tools and evaluation, on a GPU or the CPU. Our own service over the in-process adapters by default, TEI or vLLM when throughput matters." "Python, FastAPI, explorer_models_local"
            }
            group "Data" {
                database = container "Database" "Catalog, chunks, indexes, map data and caches, one writer per schema." "PostgreSQL, pgvector" "Database"
                files = container "File storage" "Results of cluster jobs (vectors, map builds) with their manifests, kept for a repeated import, and PDFs for own text extraction. Used only by the batch tools." "File system" "Database"
            }
            group "Batch" {
                batchTools = container "Batch tools" "Synchronization with DSpace, chunking, index builds and imports, map builds. Started by cron on the serving node, heavy jobs on the cluster (SLURM) or MetaCentrum (PBS)." "Python, explorer_batch"
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
