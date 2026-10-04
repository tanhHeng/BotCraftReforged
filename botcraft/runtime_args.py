from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeArgs:
    generate_default_only: bool = False
    initialize_environment: bool = False
    auto_init: bool = False
    config_file_path: str = 'config.yml'
    permission_file_path: str = 'permissions.yml'
    check_capabilities: bool = False
