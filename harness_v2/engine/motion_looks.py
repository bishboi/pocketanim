"""The engine's looks: each a whole design -- colours, fonts, the board's texture, how cards, photos and stamps
are dressed -- and a whole way of moving: how long things take, how they ease, how much they overshoot, how one
picture gives way to the next, how things idle while the voice goes on, and what they sound like.

A look is registered as a style of the lecture engine (pocket_lecture.register_style), so everything the engine
draws -- captions, maps, diagrams, the side panel -- is in its colours and fonts too; the motion engine (motion.py)
reads the look's `motion` entry for the rest.

    paper      a cream explainer page: bold condensed heads, mono kickers, white cards with soft shadows, a yellow
               highlight, red stamps. Snappy, with overshoot; pictures slide in and out.
    newsroom   a dark documentary collage: halftone grain, cutouts with a white sticker edge, red and cream, a red
               wipe between pictures. Punchy.
    chalk      a charcoal chalkboard as a science channel has it: soft chalk, clean white words, a sky-blue accent.
               Calm; pictures dissolve and drift.
    data       a dark data studio: glowing cards, orange, green and blue figures that count up. Lively.
    studio     a light clean studio: white cards on a pale grey, orange accents. Lively.
    sketch     a sketchbook: ink lines drawn on, hand lettering, red and blue pencil. Everything is drawn in.

Textures are made here (numpy, Pillow), once, into .cache/motion/: nothing is downloaded.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("PANIM_MOTION_CACHE") or (HERE / ".cache" / "motion"))
TEXTURE_VERSION = 3

# ---------------------------------------------------------------- motion tokens ----------------------------------------
# Seconds and ease per kind of motion; a look scales them by its energy. The rates named are all ones the phones'
# players have (export_dsl.RATES): ease_out_back is the overshoot, ease_out_expo the fast arrival.
BASE_TOKENS = dict(
    fast=0.25,          # a chip, a tick, a label
    base=0.4,           # a card, a picture, a heading
    slow=0.7,           # a chart's bars, a line drawn, a map's route
    stagger=0.1,        # between the items of a list, a row of cards, a chart's bars (as a share of each one's time)
    hold=0.15,          # a breath between one moment and the next inside a template
)
TEMPLATE_MOST = 2.5     # seconds a template's whole entrance may take, at most (sped up to fit)
ENERGY = {"calm": 1.3, "lively": 1.0, "punchy": 0.8}

# ---------------------------------------------------------------- the looks -------------------------------------------
_INK_DARK = "#1D1A16"

LOOKS: dict[str, dict] = {
    "paper": dict(
        label="Paper (explainer)",
        theme=dict(
            pal=dict(SAND="#C99A2E", DUNE="#B5652A", TERRA="#B23A2A", RUST="#8E2C23", TEAL="#2F7F78",
                     RIVER="#2F6FA8", GREEN="#4E7F2F", OLIVE="#6E7A3D", CREAM="#1D1A16", MUTED="#7C7366",
                     ROSE="#C8102E", GOLD="#F2B705", VIOLET="#6D4BC2", HI="#111111", MOUNT="#9C9080"),
            bg="#EFE4CB", texture="motion", sans="Libre Franklin", serif="Oswald", upper=True,
            title_col="#1D1A16", highlight="#F5C518", panel="#EFE4CB", panel_style="rule", cap_bg="#1D1A16",
            cap_fg="#FBF6EA", cap_op=0.92, nb_fill="#E3D6B8", nb_stroke="#C9B994", nb_hi="#F4D27A",
            st_stroke="#BDAE8C", st_hi="#8C7E62", track="#DCCCA8", anim="fade", land="#F6EEDB",
            map_stroke="#4A4236", voice="af_bella"),
        motion=dict(
            energy="lively", enter="pop", exit="slide", transition="slide", idle="float",
            kicker_font="IBM Plex Mono", head_font="Oswald", number_font="Oswald", body_font="Libre Franklin",
            accent="#F5C518", accent_ink="#1D1A16", second="#9C9080", stamp="#C8102E", good="#3E8E41",
            bad="#C8102E", card="#FBF8F1", card_ink="#1D1A16", card_stroke="#D9CDB2", radius=0.06,
            shadow=(0.06, -0.09, 0.22), sticker=True, photo="card", texture="paper", sfx=True),
    ),
    "newsroom": dict(
        label="Newsroom (documentary collage)",
        theme=dict(
            pal=dict(SAND="#E8C07D", DUNE="#D9822B", TERRA="#E63946", RUST="#A4161A", TEAL="#4FB3A9",
                     RIVER="#6FA8DC", GREEN="#8FBF6A", OLIVE="#8A9A5B", CREAM="#F1E9DA", MUTED="#A39B8B",
                     ROSE="#E63946", GOLD="#F4C430", VIOLET="#B39DDB", HI="#FFFFFF", MOUNT="#C9C1B1"),
            bg="#1C1A17", texture="motion", sans="Libre Franklin", serif="Oswald", upper=True,
            title_col="#F1E9DA", highlight="#F4C430", panel="#1C1A17", panel_style="rule", cap_bg="#0B0A09",
            cap_fg="#F1E9DA", cap_op=0.88, nb_fill="#2A2723", nb_stroke="#4A453D", nb_hi="#5A2A2A",
            st_stroke="#4A453D", st_hi="#8C8273", track="#34302A", anim="fade", map_stroke="#F1E9DA",
            voice="am_michael"),
        motion=dict(
            energy="punchy", enter="drop", exit="fade", transition="wipe", idle="float",
            kicker_font="IBM Plex Mono", head_font="Oswald", number_font="Oswald", body_font="Libre Franklin",
            accent="#E63946", accent_ink="#FFFFFF", second="#F1E9DA", stamp="#E63946", good="#8FBF6A",
            bad="#E63946", card="#F1E9DA", card_ink="#1C1A17", card_stroke="#F1E9DA", radius=0.02,
            shadow=(0.08, -0.1, 0.45), sticker=True, photo="halftone", texture="grain", sfx=True),
    ),
    "chalk": dict(
        label="Chalk (science channel)",
        theme=dict(
            pal=dict(SAND="#F2D45C", DUNE="#F0A35E", TERRA="#EF7D6B", RUST="#C9574A", TEAL="#7FD6C8",
                     RIVER="#5AB4F0", GREEN="#9BD67E", OLIVE="#B5C77A", CREAM="#F4F4F0", MUTED="#B8B8B2",
                     ROSE="#F28B9A", GOLD="#F2D45C", VIOLET="#B9A6F5", HI="#FFFFFF", MOUNT="#DADAD4"),
            bg="#2F3031", texture="motion", sans="Poppins", serif="Poppins", upper=False, title_col="#F4F4F0",
            panel="#2F3031", panel_style="marker", cap_bg="#1A1B1C", cap_fg="#F4F4F0", cap_op=0.85,
            nb_fill="#3A3B3C", nb_stroke="#5C5D5E", nb_hi="#46505A", st_stroke="#5C5D5E", st_hi="#9EA0A2",
            track="#454647", anim="write", map_stroke="#F4F4F0", voice="am_adam"),
        motion=dict(
            energy="calm", enter="rise", exit="fade", transition="dissolve", idle="drift",
            kicker_font="Poppins", head_font="Poppins", number_font="Poppins", body_font="Poppins",
            accent="#5AB4F0", accent_ink="#0F1A22", second="#F2D45C", stamp="#F28B9A", good="#9BD67E",
            bad="#F28B9A", card="#3A3B3C", card_ink="#F4F4F0", card_stroke="#F4F4F0", radius=0.04,
            shadow=(0.05, -0.07, 0.35), sticker=False, photo="polaroid", texture="chalk", sfx=True),
    ),
    "data": dict(
        label="Data (dark studio)",
        theme=dict(
            pal=dict(SAND="#FF9F43", DUNE="#FF7F50", TERRA="#FF6B6B", RUST="#D9534F", TEAL="#2ED5C4",
                     RIVER="#4DA3FF", GREEN="#2ED573", OLIVE="#A3CB38", CREAM="#EEF2FA", MUTED="#8A96B0",
                     ROSE="#FF6B81", GOLD="#FFC75F", VIOLET="#A58BFF", HI="#FFFFFF", MOUNT="#B8C2D9"),
            bg="#0D1220", texture="motion", sans="Poppins", serif="Poppins", upper=True, title_col="#EEF2FA",
            panel="#121A2E", panel_style="solid", cap_bg="#070A12", cap_fg="#EEF2FA", cap_op=0.85,
            nb_fill="#172036", nb_stroke="#2B3757", nb_hi="#24324F", st_stroke="#2B3757", st_hi="#5D6E96",
            track="#1D2742", anim="fade", map_stroke="#B8C2D9", voice="af_sarah"),
        motion=dict(
            energy="lively", enter="rise", exit="fade", transition="zoom", idle="float",
            kicker_font="IBM Plex Mono", head_font="Poppins", number_font="Poppins", body_font="Poppins",
            accent="#FF9F43", accent_ink="#0D1220", second="#4DA3FF", stamp="#FF6B6B", good="#2ED573",
            bad="#FF6B6B", card="#172036", card_ink="#EEF2FA", card_stroke="#2B3757", radius=0.12,
            shadow=(0.0, -0.08, 0.5), sticker=False, photo="rounded", texture="glow", glow=True, sfx=True),
    ),
    "studio": dict(
        label="Studio (light, clean)",
        theme=dict(
            pal=dict(SAND="#E58E26", DUNE="#E07A5F", TERRA="#D64933", RUST="#A63A2A", TEAL="#14897F",
                     RIVER="#2E6FD8", GREEN="#2E9E5B", OLIVE="#7A8B2E", CREAM="#1D2430", MUTED="#6A7385",
                     ROSE="#D64545", GOLD="#E5A126", VIOLET="#6A4BD6", HI="#0B0F17", MOUNT="#9AA3B5"),
            bg="#ECEFF3", texture="motion", sans="Poppins", serif="Poppins", upper=False, title_col="#1D2430",
            panel="#FFFFFF", panel_style="solid", cap_bg="#1D2430", cap_fg="#FFFFFF", cap_op=0.92,
            nb_fill="#FFFFFF", nb_stroke="#D5DAE3", nb_hi="#FCE6CC", st_stroke="#D5DAE3", st_hi="#9AA3B5",
            track="#DDE2EA", anim="fade", land="#FFFFFF", map_stroke="#1D2430", voice="af_bella"),
        motion=dict(
            energy="lively", enter="rise", exit="slide", transition="push", idle="float",
            kicker_font="IBM Plex Mono", head_font="Poppins", number_font="Poppins", body_font="Poppins",
            accent="#E58E26", accent_ink="#FFFFFF", second="#2E6FD8", stamp="#D64545", good="#2E9E5B",
            bad="#D64545", card="#FFFFFF", card_ink="#1D2430", card_stroke="#D5DAE3", radius=0.14,
            shadow=(0.0, -0.07, 0.16), sticker=True, photo="rounded", texture="soft", sfx=True),
    ),
    "sketch": dict(
        label="Sketch (sketchbook)",
        theme=dict(
            pal=dict(SAND="#C0392B", DUNE="#D35400", TERRA="#C0392B", RUST="#922B21", TEAL="#16A085",
                     RIVER="#2471A3", GREEN="#239B56", OLIVE="#7D8F2A", CREAM="#1B1B1B", MUTED="#6B6B6B",
                     ROSE="#C0392B", GOLD="#D4A017", VIOLET="#7D3C98", HI="#111111", MOUNT="#8C8C8C"),
            bg="#F6F3EC", texture="motion", sans="Patrick Hand", serif="Permanent Marker", upper=False,
            title_col="#1B1B1B", panel="#F6F3EC", panel_style="marker", cap_bg="#1B1B1B", cap_fg="#FFFFFF",
            cap_op=0.9, nb_fill="#EDE8DC", nb_stroke="#C9C2B2", nb_hi="#F6D5C8", st_stroke="#BDB6A6",
            st_hi="#8F897B", track="#E3DDCF", anim="write", land="#FFFFFF", map_stroke="#1B1B1B",
            voice="am_eric"),
        motion=dict(
            energy="lively", enter="write", exit="fade", transition="page", idle="boil",
            kicker_font="Patrick Hand", head_font="Permanent Marker", number_font="Permanent Marker",
            body_font="Patrick Hand", accent="#C0392B", accent_ink="#FFFFFF", second="#2471A3", stamp="#C0392B",
            good="#239B56", bad="#C0392B", card="#FFFFFF", card_ink="#1B1B1B", card_stroke="#1B1B1B", radius=0.03,
            shadow=(0.04, -0.05, 0.12), sticker=True, photo="tape", texture="sketch", sfx=True),
    ),
    # ---- more looks: each its own board, type, colours and way of moving
    "archive": dict(
        label="Archive (sepia, typewriter)",
        theme=dict(
            pal=dict(SAND="#A0712F", DUNE="#8C5A2B", TERRA="#8E3B2E", RUST="#6E2A20", TEAL="#4C6E66",
                     RIVER="#3F5F78", GREEN="#56683A", OLIVE="#6B6A3A", CREAM="#2B2116", MUTED="#7A6A55",
                     ROSE="#9B2D20", GOLD="#B8862D", VIOLET="#5E4A6E", HI="#1A130C", MOUNT="#8F7E66"),
            bg="#E6D7B8", texture="motion", sans="EB Garamond", serif="EB Garamond", upper=False,
            title_col="#2B2116", highlight="#D9B65C", panel="#E6D7B8", panel_style="rule", cap_bg="#2B2116",
            cap_fg="#F3E9D2", cap_op=0.9, nb_fill="#DCCBA6", nb_stroke="#B9A27A", nb_hi="#E9C98A",
            st_stroke="#B9A27A", st_hi="#7A6A55", track="#D3C19A", anim="fade", land="#EFE4CB",
            map_stroke="#3A2C1C", voice="am_eric"),
        motion=dict(
            energy="calm", enter="ink", exit="fade", transition="dissolve", idle="flicker",
            kicker_font="IBM Plex Mono", head_font="EB Garamond", number_font="EB Garamond", body_font="EB Garamond",
            accent="#9B2D20", accent_ink="#F6EEDC", second="#3F5F78", stamp="#9B2D20", good="#56683A",
            bad="#9B2D20", card="#F3E9D2", card_ink="#2B2116", card_stroke="#B9A27A", radius=0.01,
            shadow=(0.05, -0.07, 0.25), sticker=False, photo="tape", texture="archive", sfx=True),
    ),
    "neon": dict(
        label="Neon (night, glowing)",
        theme=dict(
            pal=dict(SAND="#FFD166", DUNE="#FF8A5B", TERRA="#FF4D6D", RUST="#C9184A", TEAL="#2EE6D6",
                     RIVER="#4CC9F0", GREEN="#80FFDB", OLIVE="#B5E48C", CREAM="#F2EEFF", MUTED="#9A8FC7",
                     ROSE="#FF3EA5", GOLD="#FFD166", VIOLET="#B388FF", HI="#FFFFFF", MOUNT="#C3B8F0"),
            bg="#0B0620", texture="motion", sans="Quicksand", serif="Quicksand", upper=True, title_col="#F2EEFF",
            panel="#120A30", panel_style="solid", cap_bg="#05020F", cap_fg="#F2EEFF", cap_op=0.85,
            nb_fill="#170E3A", nb_stroke="#3B2A7A", nb_hi="#2A1A5E", st_stroke="#3B2A7A", st_hi="#7F6CC9",
            track="#1D1245", anim="fade", map_stroke="#C3B8F0", voice="af_sarah"),
        motion=dict(
            energy="punchy", enter="iris", exit="fade", transition="flash", idle="breathe",
            kicker_font="IBM Plex Mono", head_font="Quicksand", number_font="Quicksand", body_font="Quicksand",
            accent="#FF3EA5", accent_ink="#0B0620", second="#26E6FF", stamp="#FFD166", good="#80FFDB",
            bad="#FF4D6D", card="#170E3A", card_ink="#F2EEFF", card_stroke="#FF3EA5", radius=0.14,
            shadow=(0.0, -0.06, 0.6), sticker=False, photo="rounded", texture="neon", glow=True, sfx=True),
    ),
    "brush": dict(
        label="Brush (ink on rice paper)",
        theme=dict(
            pal=dict(SAND="#B08D57", DUNE="#9C6B3E", TERRA="#C23B22", RUST="#8E2A17", TEAL="#3E6B63",
                     RIVER="#365F7A", GREEN="#4F6B3A", OLIVE="#6E6F45", CREAM="#1B1A18", MUTED="#7B746A",
                     ROSE="#C23B22", GOLD="#B8892F", VIOLET="#5D4B6B", HI="#0D0C0B", MOUNT="#8C857A"),
            bg="#F3EEE2", texture="motion", sans="Source Sans 3", serif="Playfair Display", upper=False,
            title_col="#1B1A18", panel="#F3EEE2", panel_style="rule", cap_bg="#1B1A18", cap_fg="#F7F2E6",
            cap_op=0.9, nb_fill="#EAE3D2", nb_stroke="#C9BFA9", nb_hi="#F0D3C8", st_stroke="#C9BFA9",
            st_hi="#8C857A", track="#E2DAC6", anim="write", land="#FAF6EC", map_stroke="#1B1A18",
            voice="am_adam"),
        motion=dict(
            energy="calm", enter="ink", exit="fade", transition="dissolve", idle="drift",
            kicker_font="Source Sans 3", head_font="Playfair Display", number_font="Playfair Display",
            body_font="Source Sans 3", accent="#C23B22", accent_ink="#FFFFFF", second="#1B1A18", stamp="#C23B22",
            good="#4F6B3A", bad="#C23B22", card="#FAF6EC", card_ink="#1B1A18", card_stroke="#C9BFA9", radius=0.02,
            shadow=(0.03, -0.04, 0.12), sticker=False, photo="plain", texture="washi", sfx=True),
    ),
    "collage": dict(
        label="Collage (cut paper)",
        theme=dict(
            pal=dict(SAND="#E0A83A", DUNE="#D9822B", TERRA="#D64933", RUST="#9E2A1F", TEAL="#2A9D8F",
                     RIVER="#2E6FD8", GREEN="#5A9A3C", OLIVE="#7D8A2E", CREAM="#1F1A14", MUTED="#6D5E4C",
                     ROSE="#E23B4E", GOLD="#F2B705", VIOLET="#6D4BC2", HI="#111111", MOUNT="#9C8A72"),
            bg="#D9C3A0", texture="motion", sans="Libre Franklin", serif="Oswald", upper=True, title_col="#1F1A14",
            highlight="#F2B705", panel="#D9C3A0", panel_style="rule", cap_bg="#1F1A14", cap_fg="#FBF3E4",
            cap_op=0.92, nb_fill="#E8D7BA", nb_stroke="#B9A07C", nb_hi="#F4D27A", st_stroke="#B9A07C",
            st_hi="#6D5E4C", track="#CDB590", anim="fade", land="#F1E5CF", map_stroke="#1F1A14",
            voice="am_michael"),
        motion=dict(
            energy="punchy", enter="drop", exit="slide", transition="stack", idle="sway",
            kicker_font="IBM Plex Mono", head_font="Oswald", number_font="Oswald", body_font="Libre Franklin",
            accent="#E23B4E", accent_ink="#FFFFFF", second="#2E6FD8", stamp="#1F1A14", good="#5A9A3C",
            bad="#E23B4E", card="#FBF6EC", card_ink="#1F1A14", card_stroke="#FBF6EC", radius=0.0,
            shadow=(0.09, -0.12, 0.35), sticker=True, photo="halftone", texture="kraft", sfx=True),
    ),
    "textbook": dict(
        label="Textbook (clean grid)",
        theme=dict(
            pal=dict(SAND="#E8A33D", DUNE="#E07A5F", TERRA="#D1495B", RUST="#A23B4A", TEAL="#0F8B8D",
                     RIVER="#1F6FEB", GREEN="#2DA44E", OLIVE="#7A8B2E", CREAM="#1F2328", MUTED="#656D76",
                     ROSE="#CF222E", GOLD="#BF8700", VIOLET="#8250DF", HI="#0B0F14", MOUNT="#8C959F"),
            bg="#FFFFFF", texture="motion", sans="Source Sans 3", serif="Source Sans 3", upper=False,
            title_col="#1F2328", panel="#F6F8FA", panel_style="solid", cap_bg="#1F2328", cap_fg="#FFFFFF",
            cap_op=0.92, nb_fill="#F6F8FA", nb_stroke="#D0D7DE", nb_hi="#DDF4FF", st_stroke="#D0D7DE",
            st_hi="#8C959F", track="#EAEEF2", anim="fade", land="#FFFFFF", map_stroke="#1F2328",
            voice="af_bella"),
        motion=dict(
            energy="calm", enter="rise", exit="fade", transition="push", idle="none",
            kicker_font="IBM Plex Mono", head_font="Source Sans 3", number_font="Source Sans 3",
            body_font="Source Sans 3", accent="#1F6FEB", accent_ink="#FFFFFF", second="#8250DF", stamp="#CF222E",
            good="#2DA44E", bad="#CF222E", card="#F6F8FA", card_ink="#1F2328", card_stroke="#D0D7DE", radius=0.06,
            shadow=(0.0, -0.03, 0.08), sticker=False, photo="rounded", texture="grid", sfx=True),
    ),
    "chalkcolour": dict(
        label="Coloured chalk (green board)",
        theme=dict(
            pal=dict(SAND="#F7D774", DUNE="#F5A962", TERRA="#F28482", RUST="#D9645F", TEAL="#84DCC6",
                     RIVER="#8EC5FF", GREEN="#B5E48C", OLIVE="#C9D77A", CREAM="#F5F3EA", MUTED="#B9C2B4",
                     ROSE="#FF9AA2", GOLD="#F7D774", VIOLET="#CDB4FF", HI="#FFFFFF", MOUNT="#DCE3D6"),
            bg="#24402F", texture="motion", sans="Patrick Hand", serif="Caveat", upper=False, title_col="#F5F3EA",
            panel="#24402F", panel_style="marker", cap_bg="#132219", cap_fg="#F5F3EA", cap_op=0.85,
            nb_fill="#2E4D3A", nb_stroke="#567A63", nb_hi="#3F5E4A", st_stroke="#567A63", st_hi="#9FB6A6",
            track="#335240", anim="write", map_stroke="#F5F3EA", voice="am_adam"),
        motion=dict(
            energy="lively", enter="write", exit="fade", transition="dissolve", idle="drift",
            kicker_font="Patrick Hand", head_font="Caveat", number_font="Caveat", body_font="Patrick Hand",
            accent="#F7D774", accent_ink="#1E2B22", second="#8EC5FF", stamp="#FF9AA2", good="#B5E48C",
            bad="#FF9AA2", card="#2E4D3A", card_ink="#F5F3EA", card_stroke="#F5F3EA", radius=0.04,
            shadow=(0.04, -0.06, 0.3), sticker=False, photo="polaroid", texture="chalkgreen", sfx=True),
    ),
    "isometric": dict(
        label="Isometric (blocks on a grid)",
        theme=dict(
            pal=dict(SAND="#F4A259", DUNE="#F28F3B", TERRA="#E4572E", RUST="#B23A2A", TEAL="#17BEBB",
                     RIVER="#3D7DCA", GREEN="#5BBA6F", OLIVE="#8AA34A", CREAM="#1E2A3A", MUTED="#6B7A8F",
                     ROSE="#E4572E", GOLD="#F4A259", VIOLET="#7B6CF6", HI="#0E1724", MOUNT="#A3B0C2"),
            bg="#EEF2F7", texture="motion", sans="Poppins", serif="Poppins", upper=False, title_col="#1E2A3A",
            panel="#FFFFFF", panel_style="solid", cap_bg="#1E2A3A", cap_fg="#FFFFFF", cap_op=0.92,
            nb_fill="#FFFFFF", nb_stroke="#D3DBE6", nb_hi="#D6F5F4", st_stroke="#D3DBE6", st_hi="#A3B0C2",
            track="#DEE5EE", anim="fade", land="#FFFFFF", map_stroke="#1E2A3A", voice="af_bella"),
        motion=dict(
            energy="lively", enter="rise", exit="slide", transition="push", idle="float",
            kicker_font="IBM Plex Mono", head_font="Poppins", number_font="Poppins", body_font="Poppins",
            accent="#17BEBB", accent_ink="#FFFFFF", second="#F4A259", stamp="#E4572E", good="#5BBA6F",
            bad="#E4572E", card="#FFFFFF", card_ink="#1E2A3A", card_stroke="#D3DBE6", radius=0.1,
            shadow=(0.12, -0.12, 0.18), sticker=True, photo="rounded", texture="iso", sfx=True),
    ),
    "drafting": dict(
        label="Drafting (blueprint lines)",
        theme=dict(
            pal=dict(SAND="#FFE08A", DUNE="#FFB86B", TERRA="#FF8A80", RUST="#E57373", TEAL="#80DEEA",
                     RIVER="#B3E5FC", GREEN="#C5E1A5", OLIVE="#DCE775", CREAM="#EAF4FF", MUTED="#9FB8D6",
                     ROSE="#FF8A80", GOLD="#FFE08A", VIOLET="#D1C4E9", HI="#FFFFFF", MOUNT="#C4D7EE"),
            bg="#12355B", texture="motion", sans="IBM Plex Mono", serif="Oswald", upper=True, title_col="#EAF4FF",
            panel="#12355B", panel_style="rule", cap_bg="#0A2140", cap_fg="#EAF4FF", cap_op=0.85,
            nb_fill="#17406B", nb_stroke="#5B86B8", nb_hi="#225080", st_stroke="#5B86B8", st_hi="#9FB8D6",
            track="#1B4775", anim="write", map_stroke="#EAF4FF", voice="am_michael"),
        motion=dict(
            energy="lively", enter="write", exit="fade", transition="turn", idle="none",
            kicker_font="IBM Plex Mono", head_font="Oswald", number_font="Oswald", body_font="IBM Plex Mono",
            accent="#FFE08A", accent_ink="#12355B", second="#80DEEA", stamp="#FF8A80", good="#C5E1A5",
            bad="#FF8A80", card="#17406B", card_ink="#EAF4FF", card_stroke="#EAF4FF", radius=0.0,
            shadow=(0.0, 0.0, 0.0), sticker=False, photo="plain", texture="blueprint", sfx=True),
    ),
}

# A classic style with no look of its own moves as the nearest look does (its colours and fonts stay its own).
CLASSIC_MOTION = {"vox": "paper", "parchment": "paper", "cardboard": "paper", "atlas": "data", "cosmos": "data",
                  "lab": "studio", "whiteboard": "sketch", "blueprint": "data", "chalkboard": "chalk",
                  "friendly": "studio", "ink": "sketch", "water": "studio"}
ENTRANCES = ("pop", "rise", "drop", "slide", "write", "fade", "zoom", "flip")
EXITS = ("slide", "fade", "shrink", "drop")
TRANSITIONS = ("slide", "push", "wipe", "dissolve", "zoom", "page", "cut", "whip", "stack", "flash", "turn", "match")
IDLES = ("float", "drift", "boil", "breathe", "sway", "parallax", "flicker", "none")
ENTRANCES = ENTRANCES + ("unfold", "typewrite", "ink", "stamp", "spin", "iris")


# How each look's drawn shapes are dressed (artstyle.py). Its pictures are asked of the image model in the words
# their writer chose (genimage.prompt_for): a look sets no picture style.
# The classic style each look rests on: the scene names it (LECTURE_STYLE) so the voice tools, which read the
# scene's style before the engine is imported, find a style they know, and the look speaks with its voice.
BASE = {"paper": "vox", "newsroom": "atlas", "chalk": "chalkboard", "data": "cosmos", "studio": "lab",
        "sketch": "whiteboard", "archive": "parchment", "neon": "cosmos", "brush": "parchment", "collage": "cardboard",
        "textbook": "lab", "chalkcolour": "chalkboard", "isometric": "lab", "drafting": "blueprint"}
ART = {"paper": "clean", "newsroom": "detailed", "chalk": "chalk", "data": "clean", "studio": "clean",
       "sketch": "sketch", "archive": "detailed", "neon": "neon", "brush": "watercolour", "collage": "detailed",
       "textbook": "clean", "chalkcolour": "chalk", "isometric": "clean", "drafting": "clean"}


def register_all() -> None:
    """Every look as a lecture style (pocket_lecture.THEMES), so a scene can use_style() it by name."""
    import pocket_lecture as pl

    for name, look in LOOKS.items():
        if name not in pl.THEMES:
            pl.THEMES[name] = dict(look["theme"], label=look["label"], motion=look["motion"],
                                   voice=pl.THEMES[BASE[name]]["voice"], base_style=BASE[name])
    import artstyle

    for name, art in ART.items():
        artstyle.TEMPLATE_ART.setdefault(name, art)


def motion_of(style: str, energy: str | None = None, overrides: dict | None = None) -> dict:
    """The motion settings for a style: a look's own, or for a classic style the nearest look's (CLASSIC_MOTION);
    with `energy` (calm, lively, punchy) and any overrides. Times in `t` are the base tokens scaled by the energy."""
    look = LOOKS.get(style) or LOOKS[CLASSIC_MOTION.get(style, "paper")]
    m = dict(look["motion"])
    if style not in LOOKS:
        # A classic style keeps its own colours: the look's accent and cards come from the style's palette instead.
        m["classic"] = True
    if overrides:
        m.update({k: v for k, v in overrides.items() if v is not None})
    energy = energy or m.get("energy", "lively")
    k = ENERGY.get(energy, 1.0)
    m["energy"] = energy
    m["t"] = {name: round(v * k, 3) for name, v in BASE_TOKENS.items()}
    return m


# ---------------------------------------------------------------- textures -------------------------------------------
W, H = 1280, 720        # the frame's texture, in pixels (16:9); stretched over the frame and a little past it


def _noise(rng, shape, scale: int) -> np.ndarray:
    """Smooth value noise in 0..1: random values on a coarse grid, enlarged with bilinear interpolation."""
    from PIL import Image

    gh, gw = max(2, shape[0] // scale + 2), max(2, shape[1] // scale + 2)
    grid = (rng.random((gh, gw)) * 255).astype(np.uint8)
    big = Image.fromarray(grid).resize((shape[1], shape[0]), Image.BICUBIC)
    return np.asarray(big, dtype=np.float32) / 255.0


def _hex(colour: str) -> np.ndarray:
    h = colour.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def _vignette(strength: float, cx: float = 0.5, cy: float = 0.45) -> np.ndarray:
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((x / W - cx) * 1.25) ** 2 + ((y / H - cy) * 1.0) ** 2)
    return 1.0 - strength * np.clip(d / 0.75, 0, 1) ** 2


def texture_file(kind: str, bg: str) -> Path | None:
    """The look's board, as a PNG (made once): paper fibre and blotches, newsroom grain, chalk dust, a data studio's
    glow, a studio's soft light, a sketchbook's page. None for a kind not made here."""
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / f"tex-{kind}-{bg.lstrip('#')}-v{TEXTURE_VERSION}.png"
    if out.exists():
        return out
    from PIL import Image

    rng = np.random.default_rng(11)
    base = _hex(bg)
    img = np.ones((H, W, 3), dtype=np.float32) * base
    if kind == "paper":
        blot = _noise(rng, (H, W), 160) - 0.5
        fibre = _noise(rng, (H, W), 6) - 0.5
        img += (blot * 22 + fibre * 7)[..., None]
        img *= _vignette(0.16)[..., None]
        # A warm light from the upper left.
        y, x = np.mgrid[0:H, 0:W].astype(np.float32)
        img += (12 * (1 - np.clip(np.sqrt((x / W - 0.3) ** 2 + (y / H - 0.25) ** 2) / 0.8, 0, 1)))[..., None]
    elif kind == "grain":
        grain = rng.normal(0, 1, (H, W)).astype(np.float32)
        blot = _noise(rng, (H, W), 200) - 0.5
        img += (grain * 6 + blot * 26)[..., None]
        img *= _vignette(0.45)[..., None]
        # Halftone dots, faint, in one corner band.
        y, x = np.mgrid[0:H, 0:W].astype(np.float32)
        cell = 12
        r = (np.clip(1 - x / W, 0, 1) * 0.5 + 0.1) * cell * 0.45
        d = np.sqrt((x % cell - cell / 2) ** 2 + (y % cell - cell / 2) ** 2)
        dots = (d < r).astype(np.float32) * (y / H < 0.55) * np.clip(0.6 - x / W, 0, 1)
        img += (dots * 14)[..., None]
    elif kind == "chalk":
        smudge = _noise(rng, (H, W), 120) - 0.5
        dust = rng.random((H, W)).astype(np.float32)
        wipes = _noise(rng, (H, W), 40) - 0.5
        img += (smudge * 46 + wipes * 14 + (dust > 0.975) * 26 + (rng.normal(0, 1, (H, W)) * 5))[..., None]
        img *= _vignette(0.38)[..., None]
    elif kind == "glow":
        y, x = np.mgrid[0:H, 0:W].astype(np.float32)
        for cx, cy, col, k in ((0.2, 0.85, "#FF7A1A", 0.42), (0.85, 0.15, "#2D5BFF", 0.32)):
            d = np.sqrt(((x / W - cx) * 1.4) ** 2 + (y / H - cy) ** 2)
            glow = np.clip(1 - d / 0.85, 0, 1) ** 2.2 * k
            img = img * (1 - glow[..., None]) + _hex(col) * 0.55 * glow[..., None] + img * 0
        img += rng.normal(0, 1.6, (H, W, 1)).astype(np.float32)
    elif kind == "soft":
        y, x = np.mgrid[0:H, 0:W].astype(np.float32)
        light = 1 - np.clip(np.sqrt(((x / W - 0.5) * 1.3) ** 2 + (y / H - 0.35) ** 2) / 0.9, 0, 1)
        img += (light * 10)[..., None]
        img *= _vignette(0.07)[..., None]
    elif kind == "sketch":
        fibre = _noise(rng, (H, W), 5) - 0.5
        blot = _noise(rng, (H, W), 180) - 0.5
        img += (fibre * 6 + blot * 10)[..., None]
        # A faint dotted grid, as on a sketchbook page.
        y, x = np.mgrid[0:H, 0:W]
        grid = ((x % 32 == 0) & (y % 32 == 0)).astype(np.float32)
        img -= (grid * 40)[..., None]
        img *= _vignette(0.08)[..., None]
    elif kind == "archive":
        # Old paper: blotches and foxing, darker toward the edges as if burnt by years of light.
        blot = _noise(rng, (H, W), 120) - 0.5
        fibre = _noise(rng, (H, W), 5) - 0.5
        spots = (rng.random((H, W)) > 0.9993).astype(np.float32)
        from PIL import Image as _I, ImageFilter as _F
        foxing = np.asarray(_I.fromarray((spots * 255).astype(np.uint8)).filter(_F.GaussianBlur(5)), dtype=np.float32)
        img += (blot * 30 + fibre * 8)[..., None]
        img -= (foxing * 0.9)[..., None] * np.array([0.6, 0.8, 1.0])
        img *= _vignette(0.42)[..., None]
    elif kind == "neon":
        y, x = np.mgrid[0:H, 0:W].astype(np.float32)
        for cx, cy, col, k in ((0.15, 0.2, "#FF3EA5", 0.35), (0.88, 0.85, "#26E6FF", 0.32)):
            d = np.sqrt(((x / W - cx) * 1.4) ** 2 + (y / H - cy) ** 2)
            glow = np.clip(1 - d / 0.8, 0, 1) ** 2.4 * k
            img = img * (1 - glow[..., None]) + _hex(col) * 0.5 * glow[..., None]
        # A faint perspective grid in the lower third, as a synthwave floor.
        floor = (y / H > 0.72)
        lines = ((np.abs(((x / W - 0.5) * 40 / np.maximum(y / H - 0.6, 0.05)) % 4) < 0.08) |
                 (np.abs((1 / np.maximum(y / H - 0.65, 0.02)) % 3) < 0.25)) & floor
        img += (lines.astype(np.float32) * 22)[..., None] * np.array([1.0, 0.4, 0.9])
        img += rng.normal(0, 1.4, (H, W, 1)).astype(np.float32)
    elif kind == "washi":
        fibre = _noise(rng, (H, W), 3) - 0.5
        long = _noise(rng, (H // 4, W), 2) - 0.5
        from PIL import Image as _I
        streaks = np.asarray(_I.fromarray(((long + 0.5) * 255).astype(np.uint8)).resize((W, H)), dtype=np.float32) / 255 - 0.5
        blot = _noise(rng, (H, W), 200) - 0.5
        img += (fibre * 7 + streaks * 9 + blot * 12)[..., None]
        img *= _vignette(0.1)[..., None]
    elif kind == "kraft":
        fibre = _noise(rng, (H, W), 4) - 0.5
        blot = _noise(rng, (H, W), 90) - 0.5
        flecks = (rng.random((H, W)) > 0.996).astype(np.float32)
        img += (fibre * 14 + blot * 22 - flecks * 40)[..., None]
        img *= _vignette(0.2)[..., None]
    elif kind == "grid":
        y, x = np.mgrid[0:H, 0:W]
        minor = ((x % 24 == 0) | (y % 24 == 0)).astype(np.float32)
        major = ((x % 120 == 0) | (y % 120 == 0)).astype(np.float32)
        img -= (minor * 7 + major * 10)[..., None] * np.array([1.0, 0.7, 0.3])
    elif kind == "chalkgreen":
        smudge = _noise(rng, (H, W), 110) - 0.5
        dust = rng.random((H, W)).astype(np.float32)
        wipes = _noise(rng, (H, W), 36) - 0.5
        img += (smudge * 36 + wipes * 12 + (dust > 0.978) * 24 + rng.normal(0, 1, (H, W)) * 4)[..., None]
        img *= _vignette(0.32)[..., None]
        # A wooden ledge's shadow along the foot of the board.
        y, x = np.mgrid[0:H, 0:W].astype(np.float32)
        img *= (1 - 0.25 * np.clip((y / H - 0.93) / 0.07, 0, 1))[..., None]
    elif kind == "iso":
        y, x = np.mgrid[0:H, 0:W].astype(np.float32)
        a = (x * 0.577 + y) % 36
        b = (-x * 0.577 + y) % 36
        lines = ((a < 1.2) | (b < 1.2)).astype(np.float32)
        img -= (lines * 9)[..., None] * np.array([1.0, 0.8, 0.6])
        img *= _vignette(0.06)[..., None]
    elif kind == "blueprint":
        y, x = np.mgrid[0:H, 0:W]
        minor = ((x % 20 == 0) | (y % 20 == 0)).astype(np.float32)
        major = ((x % 100 == 0) | (y % 100 == 0)).astype(np.float32)
        img += (minor * 10 + major * 22)[..., None] * np.array([0.6, 0.8, 1.0])
        img += (_noise(rng, (H, W), 150) - 0.5)[..., None] * 18
        img *= _vignette(0.3)[..., None]
    else:
        return None
    pic = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    # A palette of 96 colours: the texture's own colours are few, and the phone's library stays small.
    pic = pic.quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG).convert("RGB")
    part = out.with_suffix(f".{os.getpid()}.part.png")
    pic.save(part, optimize=True)
    part.replace(out)
    return out


# ---------------------------------------------------------------- dressed pictures -----------------------------------
DRESS_VERSION = 3


def _dressed_path(path: str, how: str) -> Path:
    import hashlib

    src = Path(path)
    try:
        stamp = f"{src.stat().st_size}-{int(src.stat().st_mtime)}"
    except OSError:
        stamp = "0"
    key = hashlib.sha1(f"{src.resolve()}|{stamp}|{how}|v{DRESS_VERSION}".encode()).hexdigest()[:16]
    CACHE.mkdir(parents=True, exist_ok=True)
    return CACHE / f"dress-{how}-{key}.png"


def _has_alpha_cutout(img) -> bool:
    if img.mode != "RGBA":
        return False
    alpha = np.asarray(img.getchannel("A"))
    return float((alpha < 16).mean()) > 0.08


def dress(path: str, how: str, max_side: int = 1100) -> tuple[str, tuple[float, float, float, float]]:
    """A picture dressed the look's way, as a new PNG, and where the picture itself sits in it (x0, y0, x1, y1 as
    shares of the new picture, so labels placed on the old one can be moved onto it):

    sticker    a cutout's own outline, thick and white, with a soft shadow under it (a collage's cut-out)
    card       a photo on white card with a soft shadow; a cutout gets the sticker
    polaroid   a photo in a polaroid's frame (wide at the foot) with a shadow
    halftone   a photo turned to a warm duotone with a halftone screen, on white card: newsprint
    rounded    a photo with round corners and a shadow
    tape       a photo on white card with two strips of tape over its top corners
    plain      as it is
    """
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    out = _dressed_path(path, how)
    meta = out.with_suffix(".box")
    if out.exists() and meta.exists():
        try:
            box = tuple(float(v) for v in meta.read_text().split(","))
            if len(box) == 4:
                return str(out), box  # type: ignore[return-value]
        except ValueError:
            pass
    img = Image.open(path)
    img.load()
    img = img.convert("RGBA")
    if max(img.size) > max_side:
        k = max_side / max(img.size)
        img = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.LANCZOS)
    cut = _has_alpha_cutout(img)
    if how in ("card", "tape", "halftone") and cut:
        how = "sticker"
    if how in ("polaroid", "rounded") and cut:
        how = "sticker"
    w, h = img.size
    side = max(w, h)
    if how == "plain":
        img.save(out)
        meta.write_text("0,0,1,1")
        return str(out), (0.0, 0.0, 1.0, 1.0)
    if how == "sticker":
        edge = max(4, int(side * 0.022))
        pad = edge * 3 + int(side * 0.03)
        canvas = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
        alpha = Image.new("L", canvas.size, 0)
        alpha.paste(img.getchannel("A"), (pad, pad))
        grown = alpha.filter(ImageFilter.MaxFilter(edge * 2 + 1))
        grown = grown.point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.GaussianBlur(1.2))
        shadow = grown.filter(ImageFilter.GaussianBlur(edge * 1.6)).point(lambda v: int(v * 0.42))
        shade = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shade.putalpha(ImageChops.offset(shadow, int(edge * 0.6), int(edge * 1.2)))
        white = Image.new("RGBA", canvas.size, (255, 255, 255, 0))
        white.putalpha(grown)
        canvas = Image.alpha_composite(canvas, shade)
        canvas = Image.alpha_composite(canvas, white)
        canvas.alpha_composite(img, (pad, pad))
        box = (pad / canvas.width, pad / canvas.height, (pad + w) / canvas.width, (pad + h) / canvas.height)
    else:
        photo = img
        if how == "halftone":
            photo = _halftone(img)
        border = int(side * (0.035 if how in ("card", "tape", "halftone") else 0.045 if how == "polaroid" else 0))
        foot = int(side * 0.16) if how == "polaroid" else border
        shadow_r = max(6, int(side * 0.02))
        pad = shadow_r * 3
        fw, fh = w + 2 * border, h + border + foot
        canvas = Image.new("RGBA", (fw + 2 * pad, fh + 2 * pad), (0, 0, 0, 0))
        mask = Image.new("L", (fw, fh), 0)
        radius = int(side * 0.045) if how == "rounded" else int(side * 0.006)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, fw - 1, fh - 1], radius=radius, fill=255)
        shadow = Image.new("L", canvas.size, 0)
        shadow.paste(mask, (pad + int(shadow_r * 0.4), pad + int(shadow_r * 0.9)))
        shadow = shadow.filter(ImageFilter.GaussianBlur(shadow_r)).point(lambda v: int(v * 0.5))
        shade = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shade.putalpha(shadow)
        canvas = Image.alpha_composite(canvas, shade)
        frame = Image.new("RGBA", (fw, fh), (252, 250, 244, 255) if how != "rounded" else (0, 0, 0, 0))
        frame.paste(photo, (border, border), photo)
        frame.putalpha(ImageChops.multiply(frame.getchannel("A"), mask) if how == "rounded" else mask)
        canvas.alpha_composite(frame, (pad, pad))
        if how == "tape":
            tape = Image.new("RGBA", (int(fw * 0.22), int(side * 0.06)), (236, 226, 190, 200))
            for x, angle in ((pad - int(fw * 0.04), 32), (pad + fw - int(fw * 0.18), -32)):
                strip = tape.rotate(angle, expand=True)
                canvas.alpha_composite(strip, (max(0, x), max(0, pad - strip.height // 2)))
        box = ((pad + border) / canvas.width, (pad + border) / canvas.height,
               (pad + border + w) / canvas.width, (pad + border + h) / canvas.height)
    part = out.with_suffix(f".{os.getpid()}.part.png")
    canvas.save(part, optimize=True)
    part.replace(out)
    meta.write_text(",".join(f"{v:.5f}" for v in box))
    return str(out), box


def _halftone(img):
    """A photo as newsprint: grey, warmed to a cream-and-ink duotone, under a fine screen of dots."""
    from PIL import Image, ImageOps

    grey = ImageOps.autocontrast(img.convert("L"), cutoff=1)
    g = np.asarray(grey, dtype=np.float32) / 255.0
    h, w = g.shape
    cell = max(3, int(max(w, h) / 220))
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    cx = (x // cell) * cell + cell / 2
    cy = (y // cell) * cell + cell / 2
    darkness = 1 - g
    r = np.sqrt(darkness) * cell * 0.62
    dots = (np.sqrt((x - cx) ** 2 + (y - cy) ** 2) < r).astype(np.float32)
    ink = np.clip(0.55 * darkness + 0.45 * dots * darkness ** 0.5, 0, 1)
    paper, inkc = _hex("#F1E9DA"), _hex("#1C1A17")
    rgb = paper * (1 - ink[..., None]) + inkc * ink[..., None]
    out = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).convert("RGBA")
    out.putalpha(img.getchannel("A"))
    return out


def ease_out_elastic(t: float) -> float:
    """A spring that overshoots twice and settles (baked: the players have no such rate)."""
    if t <= 0 or t >= 1:
        return float(min(max(t, 0), 1))
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1
