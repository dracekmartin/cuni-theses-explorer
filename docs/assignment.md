# Thesis assignment

The official assignment of the thesis as registered in the university study system
(SIS), kept verbatim in Czech. The use cases and architecture in docs/ build on it.

---

## Název

**Sémantické vyhledávání a vizualizace závěrečných prací Univerzity Karlovy** /
Semantic Search and Visualization of Charles University Theses

## Zásady pro vypracování

Univerzita Karlova zpřístupňuje desítky tisíc obhájených závěrečných prací ve svém digitálním
repozitáři [1]. Stávající vyhledávání repozitáře je založeno na lexikální shodě slov: selhává
u dotazů formulovaných jinými slovy, než jaké obsahuje text práce, a pro týž dotaz položený
česky a anglicky vrací odlišné výsledky. Zorientovat se v takovém objemu prací je proto pro
studenty i veřejnost obtížné.

Cílem práce je navrhnout, implementovat a vyhodnotit systém, který závěrečné práce zpřístupní
třemi způsoby: i) kombinovaným sémantickým a fulltextovým vyhledáváním [2,3], které je
přesnější než stávající řešení a nezávislé na jazyce dotazu i práce, ii) interaktivní
vizualizací korpusu prací, zejména grafem tematické podobnosti [4] s možností filtrování
a s generovaným vysvětlením podobnosti dvojice prací, a iii) generovaným přehledem, který
na dotaz uživatele odpoví souhrnem podloženým konkrétními pracemi z repozitáře [5].

Řešitel v rámci práce analyzuje existující přístupy, navrhne modulární architekturu
umožňující výměnu a porovnání jednotlivých komponent (zejména embedding modelů a strategií
vyhledávání), systém implementuje nad daty repozitáře a experimentálně vyhodnotí kvalitu
vyhledávání, včetně srovnání se stávajícím vyhledáváním repozitáře. Výstupem bude
funkční prototyp připravený k nasazení.

## Seznam odborné literatury

[1] Digitální repozitář Univerzity Karlovy. https://dspace.cuni.cz/

[2] Wang et al.: Multilingual E5 Text Embeddings: A Technical Report.
https://arxiv.org/abs/2402.05672

[3] Chen et al.: BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity
Text Embeddings Through Self-Knowledge Distillation. https://arxiv.org/abs/2402.03216

[4] Grootendorst: BERTopic: Neural topic modeling with a class-based TF-IDF procedure.
https://arxiv.org/abs/2203.05794

[5] Lewis et al.: Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.
NeurIPS 2020. https://arxiv.org/abs/2005.11401

## Klíčová slova

sémantické vyhledávání|vektorové embeddingy|vizualizace|RAG|závěrečné práce

semantic search|text embeddings|visualization|RAG|theses
