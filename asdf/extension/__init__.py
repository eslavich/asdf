"""
Support for plugins that extend asdf to serialize
additional custom types.
"""
from ._extension import Extension, ExtensionProxy
from ._tag import TagDefinition
from ._converter import Converter, ConverterProxy
from ._legacy import (
    AsdfExtension,
    AsdfExtensionList,
    BuiltinExtension,
    default_extensions,
    get_default_resolver,
)


__all__ = [
    # New API
    "Extension",
    "ExtensionProxy",
    "TagDefinition",
    "Converter",
    "ConverterProxy",
    # Legacy API
    "AsdfExtension",
    "AsdfExtensionList",
    "BuiltinExtension",
    "default_extensions",
    "get_default_resolver",
]
