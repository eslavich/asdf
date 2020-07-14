from pkg_resources import iter_entry_points
import warnings
from collections.abc import Mapping

from .exceptions import AsdfWarning
from .extension import AsdfExtension


RESOURCE_MAPPINGS_GROUP = "asdf.resource_mappings"
EXTENSIONS_GROUP = "asdf.extensions"
LEGACY_EXTENSIONS_GROUP = "asdf_extensions"


def get_resource_mappings():
    return _get_entry_point_elements(RESOURCE_MAPPINGS_GROUP, Mapping)


def get_extensions():
    new_style_extensions = _get_entry_point_elements(EXTENSIONS_GROUP, AsdfExtension)
    


def _get_entry_point_elements(group, element_class):
    results = []
    for entry_point in iter_entry_points(group=group):
        elements = entry_point.load()()
        for element in elements:
            if not isinstance(element, element_class):
                warnings.warn(
                    "{} is not an instance of {}.  It will be ignored.".format(element, element_class.__name__),
                    AsdfWarning
                )
            else:
                results.append(element)
    return results
