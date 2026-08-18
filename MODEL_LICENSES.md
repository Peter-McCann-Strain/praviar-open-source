# Optional model artefacts

Praviar does not distribute third-party model weights. Models are optional,
disabled unless deliberately configured, and must be obtained from their
publisher under the publisher's current terms. An upstream software licence is
not by itself proof that a particular checkpoint or its training data can be
redistributed.

| Component                    | Authoritative upstream                                                                                                                                                                                   | Observed declaration                                                                                                                                          | Archive status                                                                            |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| DECIMER Segmentation         | [article and availability statement](https://pmc.ncbi.nlm.nih.gov/articles/PMC7941967/)                                                                                                                  | MIT software; exact checkpoint scope unresolved                                                                                                               | Link only; no weight redistribution                                                       |
| MarkushGrapher / ChemicalOCR | [DS4SD/MarkushGrapher](https://github.com/DS4SD/MarkushGrapher)                                                                                                                                          | MIT repository; model cards may differ                                                                                                                        | Link only; no weight redistribution                                                       |
| MolClassifier                | [docling-project/MolClassifier](https://huggingface.co/docling-project/MolClassifier)                                                                                                                    | MIT observed in the upstream model card; checkpoint scope pending review                                                                                      | Link only; no weight redistribution                                                       |
| MolDet                       | [UniParser/MolDet](https://huggingface.co/UniParser/MolDet)                                                                                                                                              | CC-BY-NC-SA-4.0                                                                                                                                               | Non-commercial research only; disabled                                                    |
| MolGrapher                   | [DS4SD/MolGrapher](https://github.com/DS4SD/MolGrapher)                                                                                                                                                  | MIT                                                                                                                                                           | Link only; no weight redistribution                                                       |
| MolScribe                    | [thomas0809/MolScribe](https://github.com/thomas0809/MolScribe)                                                                                                                                          | MIT                                                                                                                                                           | Link only; no weight redistribution                                                       |
| MolSight                     | [official code](https://github.com/hustvl/MolSight); [referenced checkpoint](https://huggingface.co/Robert-zwr/MolSight/blob/befac2077e41f644c25b97a740c3c779c1ed34cf/pubchem_uspto_smiles_edges_30.pth) | Apache-2.0 is displayed for the code repository and model-repository metadata; the checkpoint's commercial rights and training-data provenance are unresolved | Disabled pending commercial-rights review; no automatic download or weight redistribution |
| Real-ESRGAN x2/x4            | [official releases](https://github.com/xinntao/Real-ESRGAN/releases)                                                                                                                                     | BSD-3-Clause source code; checkpoint scope unresolved                                                                                                         | Link only; disabled; no weight redistribution or automatic download                       |
| MolNexTR                     | [CYF200127/MolNexTR](https://huggingface.co/datasets/CYF200127/MolNexTR)                                                                                                                                 | Checkpoint terms and immutable provenance unresolved                                                                                                          | Link only; disabled; no weight redistribution or automatic download                       |

These observations are provenance notes, not legal advice. Before enabling a
model, verify the current upstream licence, applicable-use restrictions,
immutable revision, file checksum, serialization risk, and local policy.

The MolNexTR file exposed by its mutable upstream page has changed since an
earlier observation. Praviar therefore does not pin or accept either observed
file automatically. A rights reviewer must approve an immutable revision,
exact size, and SHA-256 before the registry can permit activation.

For MolSight, the official AAAI paper and `hustvl/MolSight` repository identify
the code project, and that repository links the checkpoint hosted by
`Robert-zwr/MolSight`. The upstream checkpoint page at revision
`befac2077e41f644c25b97a740c3c779c1ed34cf` reports SHA-256
`21be9a46b907dfcc32a24938c31ad3a8c71065db7bed542125adea4dde88d5e6`
and identifies the file as pickle-capable PyTorch data. Its model card is empty.
Repository-level Apache-2.0 labels are recorded as observations, not as proof
that the checkpoint, its training inputs, or a particular commercial use is
licensed. The registry therefore retains `pending_review`, `unapproved`, and
all acquisition and redistribution switches disabled.

Never load an untrusted `.pt`, `.pth`, `.ckpt`, or `.bin` file: common Python
model formats can execute code while deserializing. Prefer a safe serialization
where the publisher provides one.

Any future approved model must be installed into an owner-controlled model
root that is not group- or world-writable, then mounted read-only for runtime.
Activation requires both verified artifact bytes and a matching acquisition
receipt. Checksums establish identity; they do not make pickle-capable formats
safe or grant trust to another process running as the same operating-system
user.
