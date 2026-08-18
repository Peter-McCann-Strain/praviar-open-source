"""OCSR (Optical Chemical Structure Recognition) subsystem.

Provides a uniform interface to multiple OCSR tools, each running
in its own isolated virtual environment via subprocess.

Modules:
    runner          - Subprocess runner for isolated tool invocation
    preprocessing   - Image preprocessing (binarize, denoise, CLAHE, etc.)
    postprocessing  - SMILES postprocessing (canonicalize, salt removal, etc.)
    reranking       - Beam search reranking with chemical plausibility rules
    ensemble        - Multi-model fusion strategies
    classifier      - Image classification for routing (molecule/reaction/Markush/non-chemical)
    text_validation - Text cross-validation (formula, CAS, IUPAC vs OCSR)
    workers/        - Per-tool subprocess worker scripts (8 tools)
"""
