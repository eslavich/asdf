import yaml

from .versioning import AsdfVersion


class SchemaStandard:
    def __init__(self, standard_id, path):
        self.standard_id = standard_id
        self.path = path

        with open(path) as f:
            standard = yaml.safe_load(f.read())

        self.schema_ids = set(standard["schema_ids"])

    @property
    def version(self):
        return self.standard_id.rsplit("-", 1)[-1]

    @property
    def name(self):
        return self.standard_id.rsplit("-", 1)[0]


class SchemaStandardIndex:
    def __init__(self, standards):
        self._standards = standards
        self._standards_by_id = {s.standard_id: s for s in standards}

        self._latest_standards_by_name = {}
        for standard in standards:
            if (standard.name not in self._latest_standards_by_name or
                standard.version > self._latest_standards_by_name[standard.name].version):
                self._latest_standards_by_name[standard.name] = standard

    def get_schema_ids(self, override_standard_ids=None):
        override_standards_by_name = {}
        if override_standard_ids is not None:
            for standard_id in override_standard_ids:
                if not standard_id in self._standards_by_id:
                    message = (
                        f"Unrecognized standard id '{standard_id}'.  An extension package "
                        "may be missing."
                    )
                    raise ValueError(message)
                standard = self._standards_by_id[standard_id]
                override_standards_by_name[standard.name] = standard

        standards = []
        for name, standard in self._latest_standards_by_name.items():
            if name in override_standards_by_name:
                standards.append(override_standards_by_name[name])
            else:
                standards.append(standard)

        schema_ids = set()
        for standard in standards:
            schema_ids.update(standard.schema_ids)

        return schema_ids