from importlib import import_module

MODULE_TO_PACKAGE_HINTS = {
    "langchain_google_genai": "langchain-google-genai",
    "langchain_anthropic": "langchain-anthropic",
    "langchain_openai": "langchain-openai",
    "langchain_deepseek": "langchain-deepseek",
}


def _build_missing_dependency_hint(module_path: str, err: ImportError) -> str:
    module_root = module_path.split(".", 1)[0]
    missing_module = getattr(err, "name", None) or module_root
    package_name = MODULE_TO_PACKAGE_HINTS.get(module_root)
    if package_name is None:
        package_name = MODULE_TO_PACKAGE_HINTS.get(missing_module, missing_module.replace("_", "-"))
    return f"Missing dependency '{missing_module}'. Install it with `uv add {package_name}` (or `pip install {package_name}`), then restart OctoAgent."


def resolve_variable[T](
    variable_path: str,
    expected_type: type[T] | tuple[type, ...] | None = None,
) -> T:
    """Resolve and optionally type-check ``module.path:attribute``."""
    try:
        module_path, variable_name = variable_path.rsplit(":", 1)
    except ValueError as err:
        raise ImportError(f"{variable_path} is not a module.path:attribute reference") from err

    try:
        module = import_module(module_path)
    except ImportError as err:
        module_root = module_path.split(".", 1)[0]
        err_name = getattr(err, "name", None)
        if isinstance(err, ModuleNotFoundError) or err_name == module_root:
            raise ImportError(f"Could not import module {module_path}. {_build_missing_dependency_hint(module_path, err)}") from err
        raise ImportError(f"Error importing module {module_path}: {err}") from err

    try:
        variable = getattr(module, variable_name)
    except AttributeError as err:
        raise ImportError(f"Module {module_path} does not define {variable_name}") from err

    if expected_type is not None and not isinstance(variable, expected_type):
        type_name = expected_type.__name__ if isinstance(expected_type, type) else " or ".join(item.__name__ for item in expected_type)
        raise ValueError(f"{variable_path} is not an instance of {type_name}, got {type(variable).__name__}")
    return variable


def resolve_class[T](class_path: str, base_class: type[T] | None = None) -> type[T]:
    """Resolve a class and optionally validate its base class."""
    model_class = resolve_variable(class_path, expected_type=type)
    if not isinstance(model_class, type):
        raise ValueError(f"{class_path} is not a valid class")
    if base_class is not None and not issubclass(model_class, base_class):
        raise ValueError(f"{class_path} is not a subclass of {base_class.__name__}")
    return model_class
