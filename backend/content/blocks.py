"""Page sections that editors can show or hide without touching the layout.

Hidden sections are removed from the rendered page only after the text
replacements, because saved text edits are matched by position in the original
markup. Deleting the section from the source files would shift those edits.
"""

# (key, CSS selector, label shown to editors, visible by default)
PAGE_BLOCKS = {
    "index.html": (
        ("hero-buttons", ".hero-actions", "Videon päällä olevat painikkeet (Kerro tilanteestasi, Tutustu palveluihin)", False),
        ("hero-locations", ".hero-context", "Paikkakuntapalkki videon alla", True),
        ("process", ".process-section", "Ensimmäinen askel on yhteydenotto -osio", True),
        ("services", ".services-section", "Osaamisemme-osio (kolme palvelukorttia)", True),
        ("people", ".people-section", "Asiantuntijat-osio", True),
    ),
    "palvelut.html": (
        ("service-cards", ".services-gateways", "Kolme palvelualuekorttia sivun yläosassa", False),
        ("intro-photo", ".services-intro-photo", "Yläosan valokuva", True),
        ("catalog-help", ".catalog-help", "Autamme alkuun -linkki listan alla", True),
    ),
}


def blocks_for(source_file):
    return PAGE_BLOCKS.get(source_file, ())
