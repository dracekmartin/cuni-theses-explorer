workspace "Theses Explorer" "Hybrid search, topic map and AI overview over the theses of Charles University." {

    !identifiers hierarchical

    model {
        user = person "User" "Student, visitor or teacher."
        operator = person "Operator" "Library or faculty staff running the service."
        maintainer = person "Maintainer" "Developer or researcher evolving the system."

        apiClient = softwareSystem "API client" "Scripts and other tools using the public API." "External"
        explorer = softwareSystem "Theses Explorer" "Hybrid search, topic map and AI overview over the theses of Charles University."
        dspace = softwareSystem "DSpace UK" "Digital repository of Charles University, DSpace 6.4." "External"
        einfra = softwareSystem "e-INFRA CZ" "Academic OpenAI-compatible LLM API." "External"
        batch = softwareSystem "Batch compute" "MFF HPC cluster (SLURM, GPU nodes) or MetaCentrum (PBS)." "External"

        user -> explorer "Searches theses, browses the topic map, reads AI overviews" "HTTPS"
        operator -> explorer "Checks synchronization runs" "HTTPS"
        maintainer -> explorer "Defines and compares setups, runs evaluations" "CLI, HTTPS"
        apiClient -> explorer "Searches theses" "HTTPS, JSON"
        explorer -> dspace "Harvests metadata, access status and texts" "OAI-PMH, HTTPS"
        explorer -> einfra "Generates overviews and explanations, judges relevance in evaluation" "OpenAI API"
        explorer -> batch "Runs its batch jobs there (bulk embeddings, index builds, evaluation runs), fetches the results as files" "SSH, SLURM or PBS"
    }

    views {
        properties {
            "c4plantuml.tags" "true"
        }

        systemContext explorer "context" {
            include *
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
            element "External" {
                background #999999
                color #ffffff
            }
        }
    }
}
