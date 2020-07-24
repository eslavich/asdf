from . import versioning


def validate_asdf_standard_version(value):
    if value not in versioning.supported_versions:
        raise ValueError(
            "Invalid ASDF Standard version.  Supported versions: {}".format(
                ", ".join(str(v) for v in versioning.supported_versions)
            )
        )
    return str(value)
