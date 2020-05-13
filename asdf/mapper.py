from types import GeneratorType

from . import tagged
from .versioning import AsdfVersion


class AsdfMapperMeta(type):
    def __new__(mcls, name, bases, attrs):
        if "schema_ids" in attrs:
            schema_ids = set(attrs["schema_ids"])
            if any(schema_id.startswith("tag:") for schema_id in schema_ids):
                raise ValueError(f"Class '{name}' schema_ids must not be tags")
            attrs["schema_ids"] = schema_ids

        if "types" in attrs:
            types = set(attrs["types"])
            if not all(isinstance(typ, type) for typ in types):
                raise TypeError(f"Class '{name}' types must subclass type")
            attrs["types"] = types

        return super().__new__(mcls, name, bases, attrs)


class AsdfMapper(metaclass=AsdfMapperMeta):
    schema_ids = set()
    types = set()

    @classmethod
    def create_mappers(cls, extension):
        return [cls(extension, schema_id) for schema_id in cls.schema_ids]

    def __init__(self, extension, schema_id):
        self.extension = extension
        self.schema_id = schema_id

    @property
    def version(self):
        return AsdfVersion(self.schema_id.rsplit("-", 1)[-1])

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
            return tagged.tag_object(self.schema_id, node, ctx=ctx)


class MapperIndex:
    def __init__(self, standard_index, mappers):
        self._standard_index = standard_index
        self._mappers_by_schema_id = {}
        self._mappers_by_type_by_schema_id = {}

        for mapper in mappers:
            if mapper.schema_id in self._mappers_by_schema_id:
                other_mapper = self._mappers_by_schema_id[mapper.schema_id]
                message = (
                    f"Mapper for schema id '{mapper.schema_id}' provided by both "
                    f"{type(other_mapper.extension).__name__} and {type(mapper.extension).__name__}. "
                    "Please deselect one of the conflicting extensions."
                )
                raise ValueError(message)
            self._mappers_by_schema_id[mapper.schema_id] = mapper

            for typ in mapper.types:
                if typ not in self._mappers_by_type_by_schema_id:
                    self._mappers_by_type_by_schema_id[typ] = {}

                self._mappers_by_type_by_schema_id[typ][mapper.schema_id] = mapper


    def from_schema_id(self, schema_id):
        return self._mappers_by_schema_id.get(schema_id)

    def from_type(self, type):
        result = self._mappers_by_type_by_schema_id.get(type, {})
        schema_ids = set(result.keys())
        # TODO: This should be overridable with standards set on the AsdfFile:
        intersection = schema_ids.intersection(self._standard_index.get_schema_ids())
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