def foo():
    return [
        e
        for e in self.extensions
        if (e.default_enabled or e.always_enabled) and asdf_standard_version in e.asdf_standard_requirement
    ]
