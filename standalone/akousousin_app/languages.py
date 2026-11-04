"""Readable names from the existing catalogue, retaining codes for unlisted models."""
from functools import lru_cache
from . import catalogue, resources


@lru_cache(maxsize=None)
def label(code):
    overrides = {'en_GB': 'British English', 'en_US': 'American English'}
    name = overrides.get(code)
    if name is None:
        entry = next((v for v in catalogue.catalogue(resources.root()).values()
                      if v['language']['code'] == code), None)
        name = entry['language']['name_english'] if entry else code
    return f'{name} ({code.replace("_", "-")})' if name != code else code
