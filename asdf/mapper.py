from types import GeneratorType

from . import tagged
from .versioning import AsdfVersion


class AsdfMapperMeta(type):
    def __new__(mcls, name, bases, attrs):
        if "tags" in attrs:
            tags = set(attrs["tags"])
            attrs["tags"] = schema_ids

        if "types" in attrs:
            types = set(attrs["types"])
            if not all(isinstance(typ, type) for typ in types):
                raise TypeError(f"Class '{name}' types must subclass type")
            attrs["types"] = types

        return super().__new__(mcls, name, bases, attrs)


class AsdfMapper(metaclass=AsdfMapperMeta):
    tags = set()
    types = set()

    @classmethod
    def create_mappers(cls, extension):
        return [cls(extension, tag) for tag in cls.tags]

    def __init__(self, extension, tag):
        self.extension = extension
        self.tag = tag

    @property
    def version(self):
        return AsdfVersion(self.tag.rsplit("-", 1)[-1])

    def to_tree(self, obj, ctx):
        raise NotImplementedError("AsdfMapper subclasses must implement to_tree")

    def from_tree(self, node, ctx):
        raise NotImplementedError("AsdfMapper subclasses must implement from_tree")

    def to_tree_tagged(self, obj, ctx):
        node = self.to_tree(obj, ctx)

        if isinstance(node, GeneratorType):
            generator = node
            node = next(generator)
        else:
            generator = None

        node = self._maybe_tag_node(node, ctx)
        yield node
        if generator is not None:
            yield from generator

    def _maybe_tag_node(self, node, ctx):
        if isinstance(node, tagged.Tagged):
            return node
        else:
            return tagged.tag_object(self.tag, node, ctx=ctx)


class MapperIndex:
    def __init__(self, standard_index, mappers):
        self._standard_index = standard_index
        self._mappers_by_tag = {}
        self._mappers_by_type_by_tag = {}

        for mapper in mappers:
            if mapper.tag in self._mappers_by_tag:
                other_mapper = self._mappers_by_tag[mapper.tag]
                message = (
                    f"Mapper for tag '{mapper.tag}' provided by both "
                    f"{type(other_mapper.extension).__name__} and {type(mapper.extension).__name__}. "
                    "Please deselect one of the conflicting extensions."
                )
                raise ValueError(message)
            self._mappers_by_tag[mapper.tag] = mapper

            for typ in mapper.types:
                if typ not in self._mappers_by_type_by_tag:
                    self._mappers_by_type_by_tag[typ] = {}

                self._mappers_by_type_by_tag[typ][mapper.tag] = mapper

    def from_tag(self, tag):
        return self._mappers_by_tag.get(tag)

    def from_type(self, type):
        result = self._mappers_by_type_by_tag.get(type, {})
        tags = set(result.keys())
        # TODO: This should be overridable with standards set on the AsdfFile:
        intersection = tags.intersection(self._standard_index.get_tags())
        if len(intersection) == 0:
            return None
        elif len(intersection) == 1:
            return result[intersection.pop()]
        else:
            # TODO: Make this message more helpful
            message = (
                f"Ambiguous mapper support for type '{type.__name__}'."
            )
            raise ValueError(message)