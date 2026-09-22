---
id: 6
title: What the pipeline produces between content and scene
labels: [wayfinder:grilling]
parent: 1
blocked_by: []
assignee: null
state: open
---

## Question

The brief names three steps — content in, describe the scene / generate a
transcript, generate the video — but not what exists between them. Decide the
intermediate artifacts, and for each: is it stored, is it shown to the user, and
is it editable.

Open questions inside that:

- Is the **transcript** a first-class object a user edits, or a prompt-shaping
  intermediate that never surfaces? It is the natural place for a human to steer
  meaning rather than visuals, which is the kind of feedback the brief expects.
- Is there a **scene plan** between transcript and Manim — a structured
  description of beats, or does the model go straight to Python?
- How many model calls is that, and does each step get its own, or does one call
  do several?
- Which of these are **stored** versus derived on demand? The map has settled
  that scene source and scene program are both stored; this decides what else is.
- Does a scene have **scenes** — is one generation one Manim `Scene`, or a
  sequence the phone plays in order? The library format supports many scenes;
  the player picks one.

This is the shape of the data before the schema can be drawn, which is why
[What the Supabase schema is](08-supabase-schema.md) waits on it.
