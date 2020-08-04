"""
Support for plugins that extend asdf to serialize
additional custom types.
"""
from ._extension import ExtensionProxy
from ._tag import TagDefinition
from ._legacy import (
    AsdfExtension,
    AsdfExtensionList,
    BuiltinExtension,
    default_extensions,
    get_default_resolver,
)


__all__ = [
    # New API
    "TagDefinition",
    "ExtensionProxy",
    # Legacy API
    "AsdfExtension",
    "AsdfExtensionList",
    "BuiltinExtension",
    "default_extensions",
    "get_default_resolver",
]
