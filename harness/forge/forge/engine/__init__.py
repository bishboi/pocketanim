"""The engine stages the orchestrator calls: ingest, narrate, compile, render, qa, assemble, learn.

Every stage reads the job folder and writes back into it, and each keys its
output by a hash of its inputs, so a resumed or revised job redoes only what
changed.
"""
